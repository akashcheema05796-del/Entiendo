"""V1 — edge verification from spans (PLAN_v5). "Verified, not inferred" made true.

Static import analysis proves an edge *can* fire; recorded spans prove it *did*.
These cover: span-pair matching from flat hops, the declared→verified tri-state,
staleness when the caller's code changes, the refundly integration (the pipeline's
call edges verify, the config edge stays tentative), and a fabricated never-fired
edge staying tentative + listed in `unverifiedDeclaredEdges`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import spans  # noqa: E402
from ent.extractor import extract, _composite_of  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


# --------------------------------------------------------------------------- #
# span-pair matching (flat hops → caller→callee edges)
# --------------------------------------------------------------------------- #

def test_observe_pairs_parent_to_child() -> None:
    traces = [{
        "traceId": "t1", "ts": "2026-01-01T00:00:00Z",
        "hops": [
            {"node": "a", "parent": None, "compositeVersion": "ca"},
            {"node": "b", "parent": "a", "compositeVersion": "cb"},
            {"node": "c", "parent": "a", "compositeVersion": "cc"},
        ],
    }]
    obs = spans.observe(traces)
    assert set(obs) == {("a", "b"), ("a", "c")}
    assert obs[("a", "b")].callerComposite == "ca"        # the CALLER's composite
    assert obs[("a", "b")].observationCount == 1


def test_observe_counts_and_last_seen_across_traces() -> None:
    traces = [
        {"traceId": "t1", "ts": "2026-01-01T00:00:00Z",
         "hops": [{"node": "a", "parent": None}, {"node": "b", "parent": "a"}]},
        {"traceId": "t2", "ts": "2026-01-02T00:00:00Z",
         "hops": [{"node": "a", "parent": None}, {"node": "b", "parent": "a"}]},
    ]
    obs = spans.observe(traces)
    assert obs[("a", "b")].observationCount == 2
    assert obs[("a", "b")].lastVerifiedAt == "2026-01-02T00:00:00Z"


def test_hop_with_no_parent_contributes_no_edge() -> None:
    obs = spans.observe([{"hops": [{"node": "a", "parent": None}]}])
    assert obs == {}


# --------------------------------------------------------------------------- #
# tri-state + staleness in a tmp project
# --------------------------------------------------------------------------- #

def _proj(tmp_path: Path) -> Path:
    # a declares calls b, but does NOT import it → declared-only until a span verifies
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    (tmp_path / "a" / "one.py").write_text("VALUE = 1\n")
    (tmp_path / "b" / "two.py").write_text("thing = 1\n")
    (tmp_path / "a" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: a.one\nname: a.one\nnodeKind: compute\n"
        "owner: me\nclaims:\n  - a/one.py\ncontract:\n  sideEffects: none\n"
        "dependencies:\n  calls: [b.two]\n")
    (tmp_path / "b" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: b.two\nname: b.two\nnodeKind: compute\n"
        "owner: me\nclaims:\n  - b/two.py\ncontract:\n  sideEffects: none\n")
    return tmp_path


def _trace(root: Path, caller_composite: str):
    return [{"traceId": "t", "ts": "2026-01-01T00:00:00Z", "hops": [
        {"node": "a.one", "parent": None, "compositeVersion": caller_composite},
        {"node": "b.two", "parent": "a.one", "compositeVersion": "cb"},
    ]}]


def _edge(root: Path, spans_map):
    result = extract(root, spans=spans_map)
    return next(e for e in result.graph["edges"] if e["from"] == "a.one" and e["to"] == "b.two")


def test_declared_edge_is_unverified_without_spans(tmp_path: Path) -> None:
    edge = _edge(_proj(tmp_path), None)
    assert edge["declared"] and not edge["verified"]
    assert edge["verificationSource"] == []


def test_span_verifies_declared_edge(tmp_path: Path) -> None:
    root = _proj(tmp_path)
    caller_composite = _composite_of(find_node(root, "a.one"), root)
    edge = _edge(root, spans.observe(_trace(root, caller_composite)))
    assert edge["verified"] and edge["verificationSource"] == ["span"]
    assert edge["observationCount"] == 1 and edge["lastVerifiedAt"] == "2026-01-01T00:00:00Z"


def test_stale_observation_does_not_verify(tmp_path: Path) -> None:
    root = _proj(tmp_path)
    old_composite = _composite_of(find_node(root, "a.one"), root)
    trace = _trace(root, old_composite)
    # the caller's code changes → its composite moves → the old span is stale
    (root / "a" / "one.py").write_text("VALUE = 999  # changed\n")
    new_composite = _composite_of(find_node(root, "a.one"), root)
    assert new_composite != old_composite
    edge = _edge(root, spans.observe(trace))
    assert not edge["verified"]                            # reverts to declared-only


# --------------------------------------------------------------------------- #
# refundly integration + unverifiedDeclaredEdges
# --------------------------------------------------------------------------- #

def test_refundly_call_edges_verify_from_recorded_spans() -> None:
    result = extract(REFUNDLY, spans=spans.observe_root(REFUNDLY))
    verified = {(e["from"], e["to"]) for e in result.graph["edges"]
                if e["verified"] and "span" in e["verificationSource"]}
    assert verified == {
        ("refundly.decide", "refundly.parse_email"),
        ("refundly.decide", "refundly.orders"),
        ("refundly.decide", "refundly.gateway"),
        ("refundly.decide", "refundly.ledger"),
    }
    assert result.ok


def test_config_edge_stays_declared_only_and_not_in_unverified() -> None:
    # decide→policy is a config edge — never a runtime call, so never span-verified,
    # and deliberately excluded from unverifiedDeclaredEdges (would be permanent noise)
    result = extract(REFUNDLY, spans=spans.observe_root(REFUNDLY))
    policy = next(e for e in result.graph["edges"]
                  if e["from"] == "refundly.decide" and e["to"] == "refundly.policy")
    assert not policy["verified"] and policy["kinds"] == ["config"]
    assert result.graph["unverifiedDeclaredEdges"] == []   # only the config edge is unverified


def test_fabricated_never_fired_edge_stays_tentative(tmp_path: Path) -> None:
    root = _proj(tmp_path)
    # add a second declared call edge that no trace ever exercises
    (root / "a" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: a.one\nname: a.one\nnodeKind: compute\n"
        "owner: me\nclaims:\n  - a/one.py\ncontract:\n  sideEffects: none\n"
        "dependencies:\n  calls: [b.two, c.three]\n")
    (root / "c").mkdir()
    (root / "c" / "three.py").write_text("z = 1\n")
    (root / "c" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: c.three\nname: c.three\nnodeKind: compute\n"
        "owner: me\nclaims:\n  - c/three.py\ncontract:\n  sideEffects: none\n")
    caller_composite = _composite_of(find_node(root, "a.one"), root)
    result = extract(root, spans=spans.observe(_trace(root, caller_composite)))  # only a→b fired
    fabricated = next(e for e in result.graph["edges"]
                      if e["from"] == "a.one" and e["to"] == "c.three")
    assert not fabricated["verified"]
    unv = {(u["from"], u["to"]) for u in result.graph["unverifiedDeclaredEdges"]}
    assert ("a.one", "c.three") in unv                     # listed as the honest gap
