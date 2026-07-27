"""Phase C acceptance (PLAN_v3.md §C) — the Bridge.

The steering queue is a plain, human-readable file transport: enqueue → claim →
post verdict. Tests cover the pure queue functions, the two `ent serve` endpoints
(`POST /api/steer`, `GET /api/steering`), the two MCP tools (`await_steering`,
`post_verdict`), and a scripted-fake-agent dry-run of the operator loop
(await → apply_edit → post_verdict) ending in a GREEN verdict on the dossier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import mcp_server, server, steering  # noqa: E402


def _tmp_node(tmp_path: Path) -> Path:
    """A self-contained node (no intra-project imports → deterministic reflex)."""
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True}\n"
    )
    (tmp_path / "evals" / "demo.thing").mkdir(parents=True)
    (tmp_path / "evals" / "demo.thing" / "smoke.jsonl").write_text('{"name": "s", "input": {"x": 1}}\n')
    manifest = (
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.thing\nname: Demo\nnodeKind: compute\n"
        "owner: me\nclaims: [mod.py]\n"
        "contract:\n  entrypoint: mod.py::run\n  invariants: [\"output.ok == True\"]\n  sideEffects: none\n"
        "evals:\n  tier0:\n    - type: invariant_check\n    - {type: smoke, fixture: evals/demo.thing/smoke.jsonl}\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "entiendo.node.yaml").write_text(manifest)
    return tmp_path


# --------------------------------------------------------------------------- #
# queue mechanics
# --------------------------------------------------------------------------- #

def test_enqueue_then_pending(tmp_path: Path) -> None:
    req = steering.enqueue(tmp_path, "demo.thing", "also weight recency")
    assert req["id"].startswith("steer-")
    assert req["unit"] == "demo.thing" and req["status"] == "queued"
    pend = steering.pending(tmp_path)
    assert [p["id"] for p in pend] == [req["id"]]
    # queue.jsonl is human-readable, one JSON object per line
    line = (tmp_path / "entiendo" / "steering" / "queue.jsonl").read_text().strip()
    assert json.loads(line)["instruction"] == "also weight recency"


def test_claim_next_is_once_only(tmp_path: Path) -> None:
    r1 = steering.enqueue(tmp_path, "demo.thing", "a")
    r2 = steering.enqueue(tmp_path, "demo.thing", "b")
    first = steering.claim_next(tmp_path)
    assert first["id"] == r1["id"] and first["status"] == "claimed"   # FIFO
    second = steering.claim_next(tmp_path)
    assert second["id"] == r2["id"]
    assert steering.claim_next(tmp_path) is None                       # nothing left
    assert steering.pending(tmp_path) == []                            # both claimed


def test_post_verdict_records_and_clears_pending(tmp_path: Path) -> None:
    req = steering.enqueue(tmp_path, "demo.thing", "x")
    steering.claim_next(tmp_path)
    steering.post_verdict(tmp_path, req["id"], {"verdict": "GREEN", "status": "ready-to-merge"})
    stored = steering.result_for(tmp_path, req["id"])
    assert stored["outcome"]["verdict"] == "GREEN"
    assert req["id"] in steering.results(tmp_path)
    # a resulted request is neither pending nor re-claimable
    assert steering.pending(tmp_path) == []
    poll = steering.poll(tmp_path)
    assert poll["pending"] == [] and req["id"] in poll["results"]


def test_await_steering_timeout_is_bounded(tmp_path: Path) -> None:
    assert steering.await_steering(tmp_path, timeout_s=0)["status"] == "timeout"


def test_await_steering_returns_queued_request(tmp_path: Path) -> None:
    req = steering.enqueue(tmp_path, "demo.thing", "go")
    got = steering.await_steering(tmp_path, timeout_s=0)
    assert got["id"] == req["id"] and got["status"] == "claimed"


# --------------------------------------------------------------------------- #
# ent serve endpoints
# --------------------------------------------------------------------------- #

def test_steer_endpoint_enqueues(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    status, payload = server.handle_api(root, "POST", "/api/steer",
                                        {"unit": "demo.thing", "instruction": "add a field"})
    assert status == 200 and payload["status"] == "queued"
    assert steering.pending(root)[0]["instruction"] == "add a field"


def test_steer_endpoint_validates(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    s1, _ = server.handle_api(root, "POST", "/api/steer", {"unit": "demo.thing", "instruction": "  "})
    assert s1 == 400
    s2, _ = server.handle_api(root, "POST", "/api/steer", {"unit": "nope.unit", "instruction": "x"})
    assert s2 == 404


def test_steering_poll_endpoint(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    server.handle_api(root, "POST", "/api/steer", {"unit": "demo.thing", "instruction": "x"})
    status, payload = server.handle_api(root, "GET", "/api/steering", None)
    assert status == 200
    assert len(payload["pending"]) == 1 and payload["results"] == {}


# --------------------------------------------------------------------------- #
# MCP tools
# --------------------------------------------------------------------------- #

def test_mcp_await_and_post(tmp_path: Path) -> None:
    steering.enqueue(tmp_path, "demo.thing", "x")
    got = mcp_server.tool_await_steering(tmp_path, timeout_s=0)
    assert got["unit"] == "demo.thing"
    res = mcp_server.tool_post_verdict(tmp_path, got["id"], {"verdict": "RED"})
    assert res["outcome"]["verdict"] == "RED"
    assert mcp_server.tool_await_steering(tmp_path, timeout_s=0)["status"] == "timeout"


# --------------------------------------------------------------------------- #
# the operator loop — scripted fake agent (await → apply_edit → post_verdict)
# --------------------------------------------------------------------------- #

def test_operator_loop_dry_run_ends_in_verdict(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)

    # operator steers from the Universe
    req = steering.enqueue(root, "demo.thing", "add a harmless field")

    # --- the scripted workload (what entiendo-operator tells Claude Code to do) ---
    picked = steering.await_steering(root, timeout_s=0)          # 1. await_steering
    assert picked["id"] == req["id"]
    ctx = mcp_server.tool_get_node_context(root, picked["unit"])  # 2. get_node_context
    assert "mod.py" in ctx["claimedFiles"]
    new_body = "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True, 'weighted': 1}\n"
    outcome = mcp_server.tool_apply_edit(                         # 3. apply_edit (within claims)
        root, picked["unit"], "weight recency", [{"path": "mod.py", "content": new_body}])
    assert outcome["outcome"]["verdict"] == "GREEN"
    steering.post_verdict(root, picked["id"], outcome)           # 4. post_verdict

    # --- the Universe sees the verdict; the loop is drained ---
    result = steering.result_for(root, req["id"])
    assert result["outcome"]["outcome"]["verdict"] == "GREEN"
    assert result["outcome"]["outcome"]["status"] == "ready-to-merge"
    assert steering.pending(root) == []
    assert "weighted" in (root / "mod.py").read_text()           # the edit actually landed


def test_operator_loop_rejects_out_of_claims_and_reports(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    req = steering.enqueue(root, "demo.thing", "touch a file it does not own")
    picked = steering.await_steering(root, timeout_s=0)
    outcome = mcp_server.tool_apply_edit(
        root, picked["unit"], "sneak", [{"path": "secret.py", "content": "x=1\n"}])
    assert "error" in outcome and "secret.py" in outcome["rejected"]
    steering.post_verdict(root, picked["id"], {"status": "boundary-change-required", "detail": outcome})
    assert not (root / "secret.py").exists()
    assert steering.result_for(root, req["id"])["outcome"]["status"] == "boundary-change-required"
