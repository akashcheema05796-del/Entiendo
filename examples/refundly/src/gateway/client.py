"""refundly.gateway — the external refund API (irreversible; approval-gated).

The target of issue_refund. Third-party and irreversible, so edits to this unit
require human sign-off (approval.required: true).
"""


def issue_refund(order_id, amount):
    return {"order": order_id, "refunded": amount}
