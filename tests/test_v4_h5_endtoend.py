"""V4 — H5 pre-flight: the steer → edit → propose → approve loop, end to end.

The live demo (V4.3) is human-run and screen-recorded; this is the *code* half —
a regression test that exercises the whole H5 seam through its real functions
(no mocked clocks, no fixture-only shortcuts) so the path can't rot before the
recording. Walks: steering queue → apply_edit (confined to claims) → tier0 rerun
→ proposal (working tree reverts) → approve (stored diff applied).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import mcp_server, steering  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"

NEW_GATEWAY = '''"""refundly.gateway — the external refund API (irreversible; approval-gated)."""


def execute_refund(order_id, amount, order_amount=None):
    capped = min(amount, order_amount) if order_amount is not None else amount
    return {"order": order_id, "refunded": capped, "irreversible": True}
'''


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, root)
    return root


def _gateway_src(root: Path) -> str:
    return (root / "src" / "gateway" / "client.py").read_text()


def test_h5_full_loop_steer_propose_approve(project: Path) -> None:
    root = project
    original = _gateway_src(root)

    # 1. steer the approval-gated unit
    req = steering.enqueue(root, "refundly.gateway", "clamp the refund to the order amount")
    rid = req["id"]
    assert rid.startswith("steer-")

    # 2. the operator edits through the unit (supplies content directly — no model)
    res = mcp_server.tool_apply_edit(
        root, "refundly.gateway", "clamp refund to order amount",
        [{"path": "src/gateway/client.py", "content": NEW_GATEWAY}])
    assert res["changed"] == ["src/gateway/client.py"]
    assert res["unifiedDiffs"]                          # a real diff to show
    assert "order_amount" in _gateway_src(root)         # applied live, pre-approval

    # 3. approval.required → route into a PROPOSAL: the working tree reverts
    prop = mcp_server.tool_post_verdict(root, rid, res, proposal=True)
    assert prop["unit"] == "refundly.gateway" and prop["status"] == "awaiting-approval"
    assert _gateway_src(root) == original               # held back — not live yet
    assert [p["unit"] for p in steering.proposals(root)] == ["refundly.gateway"]

    # 4. approve → the stored `after` is applied, the proposal clears
    result = steering.approve(root, rid)
    assert result["applied"] == ["src/gateway/client.py"]
    assert "order_amount" in _gateway_src(root)         # now live
    assert steering.proposals(root) == []


def test_h5_reject_leaves_working_tree_untouched(project: Path) -> None:
    root = project
    original = _gateway_src(root)
    req = steering.enqueue(root, "refundly.gateway", "clamp the refund")
    res = mcp_server.tool_apply_edit(
        root, "refundly.gateway", "clamp",
        [{"path": "src/gateway/client.py", "content": NEW_GATEWAY}])
    mcp_server.tool_post_verdict(root, req["id"], res, proposal=True)

    steering.reject(root, req["id"])
    assert _gateway_src(root) == original               # reject = no change, ever
    assert steering.proposals(root) == []


def test_h5_apply_edit_is_confined_to_claims(project: Path) -> None:
    # writing outside the unit's claims is rejected, not written (SPEC §6)
    root = project
    res = mcp_server.tool_apply_edit(
        root, "refundly.gateway", "escape the boundary",
        [{"path": "src/orders/store.py", "content": "# hijack\n"}])
    assert "error" in res and "src/orders/store.py" in res["rejected"]
    assert "hijack" not in (root / "src" / "orders" / "store.py").read_text()
