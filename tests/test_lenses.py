"""Phase 5 — lenses 2 (flow), 3 (trace), 6 (blast radius).

No formal acceptance in SPEC.md §8 for this phase; these lock in the data each
lens depends on: traffic/volume (flow), recorded hops with latency (trace), and
transitive downstream dependents ranked by coupling (blast radius).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent import history, node  # noqa: E402
from ent.render import blast_radius, build_view, render_html  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


# --------------------------------------------------------------------------- #
# lens 3 — trace
# --------------------------------------------------------------------------- #

def test_capture_trace_records_hops_with_latency(tmp_path: Path) -> None:
    @node("a.one")
    def one() -> int:
        return 1

    @node("b.two")
    def two() -> int:
        return one() + 1

    with history.capture_trace(tmp_path, trace_id="req-1", ts="t0"):
        two()

    recorded = history.traces(tmp_path)
    assert len(recorded) == 1
    hops = recorded[0]["hops"]
    assert {h["node"] for h in hops} == {"a.one", "b.two"}
    assert all("duration_ms" in h for h in hops)
    assert recorded[0]["traceId"] == "req-1"


def test_error_hop_marked_in_trace(tmp_path: Path) -> None:
    @node("x.boom")
    def boom() -> None:
        raise ValueError()

    with history.capture_trace(tmp_path, trace_id="req-err"):
        with pytest.raises(ValueError):
            boom()

    hop = history.traces(tmp_path)[0]["hops"][0]
    assert hop["status"] == "error"


# --------------------------------------------------------------------------- #
# lens 2 — flow (volume)
# --------------------------------------------------------------------------- #

def test_view_exposes_traffic_from_traces(tmp_path: Path) -> None:
    @node("a.one")
    def one() -> int:
        return 1

    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "mod").mkdir()
    (tmp_path / "mod" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: a.one\nname: A\nnodeKind: compute\n"
        "owner: me\nclaims: [a.py]\ncontract: {sideEffects: none}\n"
        "evals: {tier0: [{type: invariant_check}]}\n"
    )
    with history.capture_trace(tmp_path, trace_id="r1"):
        one()
        one()

    view = build_view(tmp_path)
    assert view["traffic"]["a.one"] == 2
    assert len(view["traces"]) == 1


# --------------------------------------------------------------------------- #
# lens 6 — blast radius
# --------------------------------------------------------------------------- #

def test_blast_radius_finds_transitive_dependents() -> None:
    view = build_view(GREENFIELD)

    # Everything that reaches config.retrieval by following edges.
    br = blast_radius(view, "config.retrieval")
    assert "retrieval.chunk_ranker" in br["dependents"]
    assert "retrieval.vector_store" in br["dependents"]
    assert "llm.gateway" in br["dependents"]

    # vector_store is depended on by the ranker.
    br2 = blast_radius(view, "retrieval.vector_store")
    assert "retrieval.chunk_ranker" in br2["dependents"]


def test_blast_radius_ranks_by_coupling() -> None:
    view = build_view(GREENFIELD)
    br = blast_radius(view, "state.doc_index")
    # Direct dependents are ranked; the ranked list is a subset of dependents.
    assert set(br["ranked"]).issubset(set(br["dependents"]))
    assert all(br["directCoupling"][n] >= 1 for n in br["ranked"])


def test_leaf_node_has_no_dependents() -> None:
    view = build_view(GREENFIELD)
    # The ranker is a root — nothing depends on it.
    br = blast_radius(view, "retrieval.chunk_ranker")
    assert br["dependents"] == []


def test_all_six_lens_tabs_in_html() -> None:
    view = build_view(GREENFIELD)
    html = render_html(view)
    for label in ("Structure", "Flow", "Trace", "Health", "Timeline", "Blast radius"):
        assert label in html
