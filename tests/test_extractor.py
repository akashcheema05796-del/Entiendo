"""L1 extractor / reconciler tests (Phase 2).

Acceptance (SPEC.md §8, Phase 2): an undeclared dependency fails the build naming
both nodes; the coverage number is correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent.extractor import extract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _node(node_id: str, *, claims: list[str], calls: list[str] | None = None) -> str:
    calls_yaml = "\n".join(f"    - {c}" for c in (calls or []))
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
  calls:
{calls_yaml}
"""


def _mkproject(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


# --------------------------------------------------------------------------- #
# greenfield
# --------------------------------------------------------------------------- #

def test_greenfield_reconciles_clean() -> None:
    result = extract(GREENFIELD)
    assert result.ok, result.errors


def test_greenfield_verified_call_edges() -> None:
    result = extract(GREENFIELD)
    verified = {
        (e["from"], e["to"]) for e in result.graph["edges"] if e["verified"]
    }
    assert ("retrieval.chunk_ranker", "retrieval.vector_store") in verified
    assert ("retrieval.chunk_ranker", "llm.gateway") in verified


def test_greenfield_coverage_is_full() -> None:
    result = extract(GREENFIELD)
    cov = result.coverage
    assert cov["coverage"] == 1.0
    assert cov["unaccountedCount"] == 0
    assert cov["claimedCount"] == 6


# --------------------------------------------------------------------------- #
# reconciliation
# --------------------------------------------------------------------------- #

def test_undeclared_dependency_fails_naming_both_nodes(tmp_path: Path) -> None:
    _mkproject(
        tmp_path,
        {
            "a/one.py": "from b.two import thing\n",
            "b/two.py": "thing = 1\n",
            "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"]),  # no deps
            "b/entiendo.node.yaml": _node("b.two", claims=["b/two.py"]),
        },
    )
    result = extract(tmp_path)
    assert not result.ok
    drift = [e for e in result.errors if "drift" in e]
    assert drift, result.errors
    assert "a.one" in drift[0] and "b.two" in drift[0]


def test_declared_dependency_is_verified_not_drift(tmp_path: Path) -> None:
    _mkproject(
        tmp_path,
        {
            "a/one.py": "from b.two import thing\n",
            "b/two.py": "thing = 1\n",
            "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"], calls=["b.two"]),
            "b/entiendo.node.yaml": _node("b.two", claims=["b/two.py"]),
        },
    )
    result = extract(tmp_path)
    assert result.ok, result.errors
    edge = next(e for e in result.graph["edges"] if e["to"] == "b.two")
    assert edge["declared"] and edge["verified"]


def test_double_claim_fails(tmp_path: Path) -> None:
    _mkproject(
        tmp_path,
        {
            "shared.py": "x = 1\n",
            "a/entiendo.node.yaml": _node("a.one", claims=["shared.py"]),
            "b/entiendo.node.yaml": _node("b.two", claims=["shared.py"]),
        },
    )
    result = extract(tmp_path)
    assert not result.ok
    assert any("claimed by multiple nodes" in e for e in result.errors)


def test_dangling_dependency_fails(tmp_path: Path) -> None:
    _mkproject(
        tmp_path,
        {
            "a/one.py": "x = 1\n",
            "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"], calls=["ghost.node"]),
        },
    )
    result = extract(tmp_path)
    assert not result.ok
    assert any("unknown node 'ghost.node'" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# coverage
# --------------------------------------------------------------------------- #

def test_coverage_counts_unaccounted(tmp_path: Path) -> None:
    _mkproject(
        tmp_path,
        {
            "a/one.py": "x = 1\n",
            "orphan.py": "y = 2\n",  # claimed by nobody, not acknowledged
            "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"]),
        },
    )
    result = extract(tmp_path)
    cov = result.coverage
    assert "orphan.py" in cov["unaccounted"]
    assert cov["coverage"] < 1.0


def test_unclaimed_list_acknowledges_files(tmp_path: Path) -> None:
    _mkproject(
        tmp_path,
        {
            "a/one.py": "x = 1\n",
            "orphan.py": "y = 2\n",
            "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"]),
            "entiendo/unclaimed.txt": "orphan.py\n",
        },
    )
    result = extract(tmp_path)
    cov = result.coverage
    assert cov["unaccountedCount"] == 0
    assert "orphan.py" in cov["acknowledgedUnclaimed"]
    assert cov["coverage"] == 1.0
