"""L5 scoped edit loop tests (Phase 6).

Acceptance (SPEC.md §8, Phase 6): picking a node and requesting a change produces
an edit confined to `claims`, with a pass/fail verdict, without loading unrelated
files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.editloop import assemble_context, check_boundary, review_edit  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


# --------------------------------------------------------------------------- #
# context assembly — "without loading unrelated files"
# --------------------------------------------------------------------------- #

def test_context_loads_only_claimed_file_bodies() -> None:
    ctx = assemble_context(GREENFIELD, "retrieval.chunk_ranker")
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    assert set(ctx.claimed_files) == set(node.claims)
    # No neighbour's source body leaks in.
    assert "src/vector_store/store.py" not in ctx.claimed_files
    joined = "\n".join(ctx.claimed_files.values())
    assert "def search" not in joined  # vector_store's body is never loaded


def test_context_includes_neighbour_contracts_only() -> None:
    ctx = assemble_context(GREENFIELD, "retrieval.chunk_ranker")
    assert set(ctx.neighbour_contracts) == {
        "retrieval.vector_store", "llm.gateway", "state.doc_index", "config.retrieval",
    }
    # Contracts, not full manifests: no `claims` key on a neighbour entry.
    for contract in ctx.neighbour_contracts.values():
        assert "claims" not in contract
        assert "sideEffects" in contract


def test_context_carries_baseline() -> None:
    ctx = assemble_context(GREENFIELD, "retrieval.chunk_ranker")
    assert ctx.baselines.get("ndcg@5") == 0.81


def test_unknown_node_raises() -> None:
    with pytest.raises(KeyError):
        assemble_context(GREENFIELD, "does.not_exist")


# --------------------------------------------------------------------------- #
# boundary enforcement — "confined to claims"
# --------------------------------------------------------------------------- #

def test_boundary_allows_claimed_file() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    br = check_boundary(node, ["src/retrieval/ranker.py"], GREENFIELD)
    assert br.within_claims
    assert not br.violations


def test_boundary_flags_unclaimed_file() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    br = check_boundary(node, ["src/vector_store/store.py"], GREENFIELD)
    assert not br.within_claims
    assert "src/vector_store/store.py" in br.violations


def test_boundary_handles_absolute_paths() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    abs_path = str(GREENFIELD / "src/retrieval/ranker.py")
    br = check_boundary(node, [abs_path], GREENFIELD)
    assert br.within_claims


# --------------------------------------------------------------------------- #
# edit review — verdict + approval gate
# --------------------------------------------------------------------------- #

def test_in_bounds_green_edit_is_ready() -> None:
    outcome = review_edit(GREENFIELD, "retrieval.chunk_ranker", ["src/retrieval/ranker.py"])
    assert outcome.boundary.within_claims
    assert outcome.verdict == "green"
    assert outcome.status == "ready-to-merge"


def test_out_of_bounds_edit_is_blocked() -> None:
    outcome = review_edit(GREENFIELD, "retrieval.chunk_ranker", ["src/vector_store/store.py"])
    assert outcome.status == "blocked: boundary-change proposal required"


def test_approval_gated_node_awaits_signoff() -> None:
    # llm.gateway has approval.required: true.
    outcome = review_edit(GREENFIELD, "llm.gateway", ["src/gateway/client.py"])
    assert outcome.approval_required
    assert outcome.status == "awaiting-signoff"


def test_review_reports_blast_radius() -> None:
    outcome = review_edit(GREENFIELD, "state.doc_index", ["src/doc_index/schema.sql"])
    # Both the ranker and the vector store depend on the doc index.
    assert "retrieval.chunk_ranker" in outcome.blast["dependents"]
    assert "retrieval.vector_store" in outcome.blast["dependents"]
