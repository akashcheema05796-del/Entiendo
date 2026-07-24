"""tier0 execution tests (Phase 7 §5, §15).

tier0 now RUNS the node over fixture rows and evaluates real invariants against
real output. Verdicts: GREEN / RED / UNTESTED / ERROR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent import verdicts  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def test_executable_greenfield_nodes_are_green() -> None:
    for node_id in ("retrieval.chunk_ranker", "retrieval.vector_store"):
        node = find_node(GREENFIELD, node_id)
        result = run_tier0(node, GREENFIELD)
        assert result.verdict == verdicts.GREEN, [c.detail for c in result.checks]


def test_no_entrypoint_nodes_are_untested() -> None:
    for node_id in ("state.doc_index", "llm.gateway", "config.retrieval"):
        node = find_node(GREENFIELD, node_id)
        result = run_tier0(node, GREENFIELD)
        assert result.verdict == verdicts.UNTESTED


def test_tier0_is_fast() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    assert run_tier0(node, GREENFIELD).duration_ms < 2000


def test_break_ranker_goes_red_with_real_numbers(tmp_path: Path) -> None:
    """The one-line test (§15): break the node, it goes red and says why."""
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")

    # An entrypoint that violates len(output.chunks) <= input.k.
    def bad(inp: dict) -> dict:
        return {"chunks": [{"id": c["id"], "score": 1.0} for c in inp["candidates"]]}

    result = run_tier0(node, GREENFIELD, entrypoint=bad)
    assert result.verdict == verdicts.RED
    failed = [c for c in result.checks if c.status == "fail"]
    assert failed and "len(output.chunks)" in failed[0].detail
    assert "input.k" in failed[0].detail  # shows the real numbers, not "assertion failed"
