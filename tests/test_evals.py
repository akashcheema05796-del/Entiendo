"""L2 tier0 eval runner tests (Phase 3).

Acceptance (SPEC.md §8, Phase 3): `ent eval <node>` returns a tier0 verdict fast.
Verifies green on the greenfield nodes and red on the failure modes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import Node, find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"

GREENFIELD_NODES = [
    "retrieval.chunk_ranker",
    "retrieval.vector_store",
    "state.doc_index",
    "llm.gateway",
    "config.retrieval",
]


@pytest.mark.parametrize("node_id", GREENFIELD_NODES)
def test_greenfield_nodes_pass_tier0(node_id: str) -> None:
    node = find_node(GREENFIELD, node_id)
    assert node is not None
    result = run_tier0(node, GREENFIELD)
    assert result.verdict == "green", [c for c in result.checks if c.status == "fail"]


def test_tier0_is_fast() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    result = run_tier0(node, GREENFIELD)
    assert result.duration_ms < 2000  # sub-2s acceptance bar


def _mknode(tmp_path: Path, manifest: dict, files: dict[str, str]) -> Node:
    import yaml

    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    path = tmp_path / "entiendo.node.yaml"
    path.write_text(yaml.safe_dump(manifest))
    return Node.from_manifest(manifest, path)


def test_malformed_invariant_is_red(tmp_path: Path) -> None:
    node = _mknode(
        tmp_path,
        {
            "id": "x.y", "name": "X", "nodeKind": "compute", "owner": "me",
            "claims": ["s.py"],
            "contract": {"invariants": ["len(output.chunks <= input.k"], "sideEffects": "none"},
            "evals": {"tier0": [{"type": "invariant_check"}]},
        },
        {"s.py": "x = 1\n"},
    )
    result = run_tier0(node, tmp_path)
    assert result.verdict == "red"
    assert any("malformed invariant" in c.detail for c in result.checks)


def test_missing_smoke_fixture_is_red(tmp_path: Path) -> None:
    node = _mknode(
        tmp_path,
        {
            "id": "x.y", "name": "X", "nodeKind": "compute", "owner": "me",
            "claims": ["s.py"],
            "contract": {"sideEffects": "none"},
            "evals": {"tier0": [{"type": "smoke", "fixture": "evals/missing.jsonl"}]},
        },
        {"s.py": "x = 1\n"},
    )
    result = run_tier0(node, tmp_path)
    assert result.verdict == "red"
    assert any("not found" in c.detail for c in result.checks)


def test_no_tier0_is_red(tmp_path: Path) -> None:
    # No node without a tier-0 eval (Invariant 3).
    node = _mknode(
        tmp_path,
        {
            "id": "x.y", "name": "X", "nodeKind": "compute", "owner": "me",
            "claims": ["s.py"], "contract": {"sideEffects": "none"},
        },
        {"s.py": "x = 1\n"},
    )
    result = run_tier0(node, tmp_path)
    assert result.verdict == "red"
