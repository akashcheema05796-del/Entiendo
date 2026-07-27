"""Phase H0 acceptance (PLAN_v4.md) — view-model completeness + the missing APIs.

- build_view exposes interior, budgets (declared + measured-from-traces),
  trajectoryVerdict, description, and playback-ready traces;
- apply_edit records a real diff + before/after verdict + behaviour delta;
- a unit with approval.required produces a proposal that approve applies and
  reject discards, with history events for both.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import history, mcp_server, server, steering  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.render import build_view  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


# --------------------------------------------------------------------------- #
# H0.1 — view model
# --------------------------------------------------------------------------- #

def test_interior_reaches_the_view() -> None:
    decide = next(n for n in build_view(REFUNDLY)["nodes"] if n["id"] == "refundly.decide")
    assert "interior" in decide
    names = {t["name"] for t in decide["interior"]["tools"]}
    assert {"order_lookup", "issue_refund"} <= names        # the core tools are present
    assert all(t.get("crosses") for t in decide["interior"]["tools"])  # each declares a crossing


def test_trajectory_verdict_in_view() -> None:
    decide = next(n for n in build_view(REFUNDLY)["nodes"] if n["id"] == "refundly.decide")
    assert decide["trajectoryVerdict"]["verdict"] == "GREEN"


def test_non_agentic_unit_has_no_interior() -> None:
    orders = next(n for n in build_view(REFUNDLY)["nodes"] if n["id"] == "refundly.orders")
    assert "interior" not in orders


def test_measured_budgets_from_traces(tmp_path: Path) -> None:
    _node(tmp_path)
    history.append_trace(tmp_path, [
        {"node": "demo.thing", "duration_ms": 100.0, "status": "ok", "cost_usd": 0.01, "tokens": 5},
        {"node": "demo.thing", "duration_ms": 300.0, "status": "ok", "cost_usd": 0.03, "tokens": 9},
    ], trace_id="t1")
    view = build_view(tmp_path)
    node = next(n for n in view["nodes"] if n["id"] == "demo.thing")
    m = node["budgets"]["measured"]
    assert m["calls"] == 2
    assert m["avgLatencyMs"] == 200.0
    assert m["avgCostUsd"] == 0.02
    # traces are playback-ready: id + ordered hops + totals
    tr = view["traces"][0]
    assert tr["id"] == "t1" and len(tr["hops"]) == 2 and tr["totalCostUsd"] == 0.04


def test_description_flows_into_view(tmp_path: Path) -> None:
    _node(tmp_path, description="Echoes the request's x back as y, for demos.")
    node = next(n for n in build_view(tmp_path)["nodes"] if n["id"] == "demo.thing")
    assert node["description"].startswith("Echoes")


# --------------------------------------------------------------------------- #
# H0.2 — diff + behaviour capture
# --------------------------------------------------------------------------- #

def test_apply_edit_captures_diff_and_verdicts(tmp_path: Path) -> None:
    _node(tmp_path)
    new = "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True, 'v': 2}\n"
    out = mcp_server.tool_apply_edit(tmp_path, "demo.thing", "bump", [{"path": "mod.py", "content": new}])
    assert "mod.py" in out["unifiedDiffs"]
    assert out["unifiedDiffs"]["mod.py"].startswith("--- a/mod.py")
    assert "+    return {'ok': True, 'v': 2}" in out["unifiedDiffs"]["mod.py"]
    assert out["verdictBefore"] == "GREEN" and out["verdictAfter"] == "GREEN"


def test_apply_edit_behaviour_delta_with_golden(tmp_path: Path) -> None:
    _golden_node(tmp_path)
    # keep it green (returns the expected output) → delta 0
    new = "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'y': req['x']}  # noop\n"
    out = mcp_server.tool_apply_edit(tmp_path, "demo.thing", "noop", [{"path": "mod.py", "content": new}])
    assert out["behaviourDelta"] is not None
    assert out["behaviourDelta"]["metric"] == "exact_match"
    assert out["behaviourDelta"]["delta"] == 0.0


# --------------------------------------------------------------------------- #
# H0.3 — approval, for real
# --------------------------------------------------------------------------- #

def _gated_edit(root: Path) -> tuple[str, dict]:
    _gated_node(root)
    req = steering.enqueue(root, "demo.gated", "tweak")
    steering.await_steering(root, timeout_s=0)
    new = "import ent\n\n@ent.node('demo.gated')\ndef run(req):\n    return {'ok': True, 'v': 2}\n"
    outcome = mcp_server.tool_apply_edit(root, "demo.gated", "tweak", [{"path": "mod.py", "content": new}])
    return req["id"], outcome


def test_proposal_holds_change_until_approved(tmp_path: Path) -> None:
    rid, outcome = _gated_edit(tmp_path)
    assert outcome["outcome"]["status"] == "awaiting-signoff"
    mcp_server.tool_post_verdict(tmp_path, rid, outcome, proposal=True)

    # the gated change is NOT live; it waits as a proposal
    assert "v': 2" not in (tmp_path / "mod.py").read_text()
    props = steering.proposals(tmp_path)
    assert len(props) == 1 and props[0]["status"] == "awaiting-approval"
    assert props[0]["unifiedDiffs"]["mod.py"]
    assert any(e.get("event") == "created" for e in history.read_events(tmp_path) if e.get("kind") == "proposal")


def test_approve_applies_the_change(tmp_path: Path) -> None:
    rid, outcome = _gated_edit(tmp_path)
    mcp_server.tool_post_verdict(tmp_path, rid, outcome, proposal=True)
    res = steering.approve(tmp_path, rid)
    assert res["applied"] == ["mod.py"]
    assert "v': 2" in (tmp_path / "mod.py").read_text()           # now live
    assert steering.proposals(tmp_path) == []
    assert any(e.get("event") == "approved" for e in history.read_events(tmp_path) if e.get("kind") == "proposal")


def test_reject_discards_the_change(tmp_path: Path) -> None:
    rid, outcome = _gated_edit(tmp_path)
    mcp_server.tool_post_verdict(tmp_path, rid, outcome, proposal=True)
    res = steering.reject(tmp_path, rid)
    assert res["rejected"] == rid
    assert "v': 2" not in (tmp_path / "mod.py").read_text()        # never applied
    assert steering.proposals(tmp_path) == []
    assert any(e.get("event") == "rejected" for e in history.read_events(tmp_path) if e.get("kind") == "proposal")


def test_proposal_endpoints(tmp_path: Path) -> None:
    rid, outcome = _gated_edit(tmp_path)
    mcp_server.tool_post_verdict(tmp_path, rid, outcome, proposal=True)

    status, payload = server.handle_api(tmp_path, "GET", "/api/proposals", None)
    assert status == 200 and len(payload["proposals"]) == 1

    status, payload = server.handle_api(tmp_path, "POST", f"/api/proposals/{rid}/approve", {})
    assert status == 200 and payload["applied"] == ["mod.py"]

    # approving again → 404 (gone)
    status, _ = server.handle_api(tmp_path, "POST", f"/api/proposals/{rid}/reject", {})
    assert status == 404


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _node(tmp_path: Path, *, description: str | None = None) -> None:
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True}\n")
    (tmp_path / "evals" / "demo.thing").mkdir(parents=True)
    (tmp_path / "evals" / "demo.thing" / "smoke.jsonl").write_text('{"name":"s","input":{"x":1}}\n')
    (tmp_path / "src").mkdir()
    desc = f"description: {json.dumps(description)}\n" if description else ""
    (tmp_path / "src" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.thing\nname: Demo\n" + desc +
        "nodeKind: compute\nowner: me\nclaims: [mod.py]\n"
        "contract: {entrypoint: mod.py::run, invariants: [\"output.ok == True\"], sideEffects: none}\n"
        "evals: {tier0: [{type: invariant_check},{type: smoke, fixture: evals/demo.thing/smoke.jsonl}]}\n")


def _golden_node(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'y': req['x']}\n")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "golden.jsonl").write_text('{"input": {"x": 1}, "expect": {"y": 1}}\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.thing\nname: Demo\nnodeKind: compute\n"
        "owner: me\nclaims: [mod.py]\n"
        "contract: {entrypoint: mod.py::run, invariants: [], sideEffects: none}\n"
        "evals:\n  tier1:\n    - type: golden\n      dataset: evals/golden.jsonl\n"
        "      humanBlessed: true\n      metric: exact_match\n      baseline: 1.0\n      minRuns: 1\n")


def _gated_node(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('demo.gated')\ndef run(req):\n    return {'ok': True}\n")
    (tmp_path / "evals" / "demo.gated").mkdir(parents=True)
    (tmp_path / "evals" / "demo.gated" / "smoke.jsonl").write_text('{"name":"s","input":{"x":1}}\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.gated\nname: Gated\nnodeKind: external\n"
        "owner: me\nclaims: [mod.py]\n"
        "contract: {entrypoint: mod.py::run, invariants: [\"output.ok == True\"], sideEffects: irreversible}\n"
        "evals: {tier0: [{type: invariant_check},{type: smoke, fixture: evals/demo.gated/smoke.jsonl}]}\n"
        "approval: {required: true}\n")
