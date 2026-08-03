"""v6 2.3 — the Bridge exercised as a real client would drive it.

Not a pre-stored diff: the edit content is GENERATED from the node context the
Bridge returns, exactly as an operator agent works — await/claim the steer, read
the scoped context, write a change derived from the actual file body, post the
verdict as a proposal, then approve through the HTTP surface and observe the
file change + the history event.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import history, mcp_server, server, steering  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def test_full_bridge_loop_with_generated_content(root: Path) -> None:
    # 1. the operator steers a gated unit from the canvas
    req = steering.enqueue(root, "refundly.gateway",
                           "guard against negative refund amounts")

    # 2. the workload claims the steer (as await_steering would hand it over)
    claimed = steering.claim_next(root)
    assert claimed and claimed["id"] == req["id"] and claimed["unit"] == "refundly.gateway"

    # 3. it reads the SCOPED context and GENERATES the edit from what it sees
    ctx = mcp_server.tool_get_node_context(root, "refundly.gateway")
    body = ctx["claimedFiles"]["src/gateway/client.py"]
    assert "def execute_refund" in body                  # derived from real context
    new_body = body.replace(
        "def execute_refund(order_id, amount):",
        "def execute_refund(order_id, amount):\n"
        "    if amount < 0:\n"
        "        raise ValueError('refund amount cannot be negative')")
    assert new_body != body

    # 4. the edit goes through the unit (claims-confined), tier0 reruns
    res = mcp_server.tool_apply_edit(root, "refundly.gateway", "guard negatives",
                                     [{"path": "src/gateway/client.py", "content": new_body}])
    assert res["changed"] == ["src/gateway/client.py"] and res["unifiedDiffs"]

    # 5. approval-gated → post_verdict routes it into a proposal (tree reverts)
    prop = mcp_server.tool_post_verdict(root, req["id"], res, proposal=True)
    assert prop["status"] == "awaiting-approval"
    assert "cannot be negative" not in (root / "src/gateway/client.py").read_text()

    # 6. the proposal is visible through the HTTP surface
    status, payload = server.handle_api(root, "GET", "/api/proposals", None)
    assert status == 200
    assert [p["unit"] for p in payload["proposals"]] == ["refundly.gateway"]

    # 7. the human approves through the same surface → file changes
    status, result = server.handle_api(
        root, "POST", f"/api/proposals/{req['id']}/approve", {})
    assert status == 200 and result["applied"] == ["src/gateway/client.py"]
    assert "cannot be negative" in (root / "src/gateway/client.py").read_text()

    # 8. and the append-only history carries the approval
    events = history.read_events(root)
    kinds = [(e.get("kind"), e.get("event")) for e in events]
    assert ("proposal", "created") in kinds and ("proposal", "approved") in kinds
