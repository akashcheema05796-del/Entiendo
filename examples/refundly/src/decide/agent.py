"""refundly.decide — the agentic unit (SPEC §14).

Parse the request, look up the order, decide refund/deny against policy, and on
refund issue it. Its interior calls tools through a **registry guard**, so an
out-of-registry call raises at runtime; the *order* of those calls is checked by
a trajectory reflex eval against a recorded run log. Neighbours see only this
unit's contract, never this interior.
"""

import ent

REGISTRY = ["order_lookup", "issue_refund"]   # interior.tools — the ONLY tools allowed

# Local stand-ins so the unit is evaluable in isolation (the law). In production
# these cross to refundly.orders / refundly.gateway — declared edges the
# reconciler verifies against interior.tools[].crosses.
def _order_lookup(order_id):
    return {"orderId": order_id, "amount": 42}


def _issue_refund(order_id, amount):
    return {"order": order_id, "refunded": amount}


@ent.node("refundly.decide")
def decide(req):
    run = []
    gate = ent.guard(REGISTRY, record_calls=run)     # runtime registry guard

    gate("order_lookup")
    order = _order_lookup(req["orderId"])

    within_policy = order["amount"] <= req.get("policyMax", 100)
    decision = "refund" if within_policy else "deny"

    if decision == "refund":
        gate("issue_refund")
        _issue_refund(order["orderId"], order["amount"])

    return {"decision": decision, "amount": order["amount"], "trajectory": run}
