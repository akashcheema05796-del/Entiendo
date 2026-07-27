"""refundly.gateway — the external refund API (irreversible; approval-gated).

Third-party and irreversible, so edits require human sign-off. This is where a
refund actually leaves the building.
"""


def execute_refund(order_id, amount):
    return {"order": order_id, "refunded": amount, "irreversible": True}
