"""`ent extract --soft` — progressive-adoption reconcile mode (gap analysis §3).

A repo mid-migration has undeclared edges (drift) everywhere until each is
declared. Soft mode reports that drift as warnings and keeps the build green,
while genuinely structural errors (double-claim, unknown-node dependency) still
fail. Default mode is unchanged: any error fails.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.commands import extract as extract_cmd  # noqa: E402
from ent.extractor import extract  # noqa: E402


def _mkproject(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _node(node_id: str, *, claims: list[str], calls: list[str] | None = None) -> str:
    calls_yaml = "[" + ", ".join(calls or []) + "]"     # valid array, [] when empty
    claims_yaml = "\n".join(f"  - {c}" for c in claims)
    return f"""\
apiVersion: entiendo/v1
kind: Node
id: {node_id}
name: {node_id}
nodeKind: compute
owner: me
claims:
{claims_yaml}
contract:
  sideEffects: none
dependencies:
  calls: {calls_yaml}
"""


def _drifted(tmp_path: Path) -> Path:
    # a.one imports b.two but doesn't declare it → drift (migration friction)
    return _mkproject(tmp_path, {
        "a/one.py": "from b.two import thing\n",
        "b/two.py": "thing = 1\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"]),
        "b/entiendo.node.yaml": _node("b.two", claims=["b/two.py"]),
    })


def _run(root: Path, *, soft: bool, check: bool = True) -> int:
    return extract_cmd._run(argparse.Namespace(root=str(root), check=check, soft=soft))


# --------------------------------------------------------------------------- #
# error classification
# --------------------------------------------------------------------------- #

def test_partition_separates_drift_from_structural(tmp_path: Path) -> None:
    root = _drifted(tmp_path)
    drift, structural = extract(root).partition_errors()
    assert drift and not structural
    assert all(e.startswith("drift:") for e in drift)


def test_structural_error_is_not_drift(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/one.py": "x = 1\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"], calls=["ghost.node"]),
    })
    drift, structural = extract(root).partition_errors()
    assert structural and not drift          # unknown-node dependency is structural


# --------------------------------------------------------------------------- #
# the CLI exit codes
# --------------------------------------------------------------------------- #

def test_soft_downgrades_drift_to_warning(tmp_path: Path, capsys) -> None:
    root = _drifted(tmp_path)
    assert _run(root, soft=True) == 0                       # build stays green
    out = capsys.readouterr().out
    assert "WARN" in out and "soft mode" in out
    assert "FAIL" not in out


def test_default_still_fails_on_drift(tmp_path: Path, capsys) -> None:
    root = _drifted(tmp_path)
    assert _run(root, soft=False) == 1                      # unchanged behaviour
    assert "FAIL" in capsys.readouterr().out


def test_soft_still_fails_on_structural_error(tmp_path: Path, capsys) -> None:
    # a file claimed by two units is structural — soft must NOT hide it
    root = _mkproject(tmp_path, {
        "shared.py": "x = 1\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["shared.py"]),
        "b/entiendo.node.yaml": _node("b.two", claims=["shared.py"]),
    })
    assert _run(root, soft=True) == 1
    assert "FAIL" in capsys.readouterr().out


def test_soft_clean_project_passes(tmp_path: Path, capsys) -> None:
    root = _mkproject(tmp_path, {
        "a/one.py": "from b.two import thing\n",
        "b/two.py": "thing = 1\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"], calls=["b.two"]),
        "b/entiendo.node.yaml": _node("b.two", claims=["b/two.py"]),
    })
    assert _run(root, soft=True) == 0
    assert "reconciled" in capsys.readouterr().out
