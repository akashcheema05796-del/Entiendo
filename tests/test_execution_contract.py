"""The execution contract (Phase 7 §1) — entrypoint resolution, drift, proposal."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent.evals.entrypoint import EntrypointDrift, resolve_entrypoint  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import Node, load  # noqa: E402
from ent import verdicts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _node(tmp_path: Path, entrypoint: str, py: str) -> Node:
    import yaml

    (tmp_path / "mod.py").write_text(py)
    raw = {
        "id": "a.b", "name": "A", "nodeKind": "compute", "owner": "me",
        "claims": ["mod.py"],
        "contract": {"entrypoint": entrypoint, "sideEffects": "none"},
    }
    path = tmp_path / "entiendo.node.yaml"
    path.write_text(yaml.safe_dump(raw))  # persist so extract() can discover it
    return Node.from_manifest(raw, path)


def test_resolve_calls_the_entrypoint(tmp_path: Path) -> None:
    node = _node(tmp_path, "mod.py::run", "def run(inp):\n    return {'ok': inp}\n")
    fn = resolve_entrypoint(node, tmp_path)
    assert fn({"x": 1}) == {"ok": {"x": 1}}


def test_decorator_mismatch_is_drift(tmp_path: Path) -> None:
    py = "import ent\n\n@ent.node('WRONG.id')\ndef run(inp):\n    return inp\n"
    node = _node(tmp_path, "mod.py::run", py)
    with pytest.raises(EntrypointDrift):
        resolve_entrypoint(node, tmp_path)


def test_extractor_reports_entrypoint_drift(tmp_path: Path) -> None:
    py = "import ent\n\n@ent.node('WRONG.id')\ndef run(inp):\n    return inp\n"
    _node(tmp_path, "mod.py::run", py)
    result = extract(tmp_path)
    assert not result.ok
    assert any("entrypoint drift" in e for e in result.errors)


def test_extractor_proposes_entrypoint_for_decorated_node() -> None:
    # llm.gateway has @ent.node but no contract.entrypoint → proposal.
    result = extract(GREENFIELD)
    proposals = result.graph["proposedEntrypoints"]
    assert proposals.get("llm.gateway") == "src/gateway/client.py::complete"


# --------------------------------------------------------------------------- #
# packaged modules: relative imports must resolve (found retrofitting a real
# library — itsdangerous — where every module does `from .exc import ...`)
# --------------------------------------------------------------------------- #

def _pkg_project(tmp_path: Path) -> Path:
    """A normal Python package: src/pkg/{__init__,errors,codec}.py, where the
    unit's module imports a sibling RELATIVELY."""
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from .codec import encode as encode\n")
    (pkg / "errors").mkdir()
    (pkg / "errors" / "__init__.py").write_text("class BadData(Exception): pass\n")
    (pkg / "codec.py").write_text(
        "from .errors import BadData\n\n"
        "def encode(value):\n"
        "    if value is None:\n"
        "        raise BadData('none')\n"
        "    return str(value).encode()\n")
    (tmp_path / "src" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: pkg.codec\nname: codec\n"
        "nodeKind: compute\nowner: me\nclaims:\n  - src/pkg/codec.py\n"
        "contract:\n  entrypoint: src/pkg/codec.py::encode\n"
        "  invariants:\n    - \"isinstance(output, bytes)\"\n"
        "  sideEffects: none\n"
        "evals:\n  tier0:\n    - type: invariant_check\n"
        "    - {type: smoke, fixture: evals/pkg.codec/smoke.jsonl}\n")
    fx = tmp_path / "evals" / "pkg.codec" / "smoke.jsonl"
    fx.parent.mkdir(parents=True)
    fx.write_text('{"name": "int", "input": 7}\n{"name": "str", "input": "hi"}\n')
    return tmp_path


def test_packaged_module_with_relative_imports_executes(tmp_path: Path) -> None:
    root = _pkg_project(tmp_path)
    node = Node.from_manifest(load(root / "src/entiendo.node.yaml"),
                              root / "src/entiendo.node.yaml")
    result = run_tier0(node, root)
    # loading codec.py as a standalone file raises "attempted relative import
    # with no known parent package" → ERROR. It must import as pkg.codec.
    assert result.verdict == verdicts.GREEN, [c.detail for c in result.checks]


def test_packaged_entrypoint_rereads_the_file_between_runs(tmp_path: Path) -> None:
    """A cached sys.modules entry would report health for code no longer on
    disk — fatal for `ent dev`, which re-evaluates in one long-lived process."""
    root = _pkg_project(tmp_path)
    mp = root / "src/entiendo.node.yaml"
    node = Node.from_manifest(load(mp), mp)
    assert run_tier0(node, root).verdict == verdicts.GREEN
    codec = root / "src/pkg/codec.py"
    codec.write_text(codec.read_text().replace("return str(value).encode()",
                                               "return str(value)"))   # no longer bytes
    assert run_tier0(node, root).verdict == verdicts.RED      # sees the NEW file
    codec.write_text(codec.read_text().replace("return str(value)",
                                               "return str(value).encode()"))
    assert run_tier0(node, root).verdict == verdicts.GREEN    # and the fix


def test_standalone_module_path_still_used(tmp_path: Path) -> None:
    from ent.evals.entrypoint import _package_context
    (tmp_path / "loose.py").write_text("def f(x): return x\n")
    assert _package_context(tmp_path / "loose.py") is None    # no __init__.py
    pkg = tmp_path / "p"; pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def f(x): return x\n")
    entry, dotted = _package_context(pkg / "m.py")
    assert entry == tmp_path and dotted == "p.m"
