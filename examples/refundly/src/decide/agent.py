"""refundly.decide — the agentic unit (SPEC §14): the pipeline's brain.

Parse → look up the order → read policy → decide refund/deny → (on refund) issue
it → write the case to the ledger. Every tool call is gated by the registry and
its *order* is checked by a trajectory reflex eval. Neighbours see this unit's
contract, never this interior.
"""

import ent

REGISTRY = ["parse", "order_lookup", "read_policy", "issue_refund", "write_ledger"]

# Local stand-ins so the unit is evaluable in isolation (the law). In production
# each crosses a border to the declared neighbour; the reconciler verifies it.
def _parse(req):
    body = req.get("email", "")
    oid = body.split("order", 1)[1].split()[0] if "order" in body else None
    return {"orderId": oid}


def _order_lookup(order_id):
    table = {"o1": {"amount": 42, "ageDays": 10}, "o2": {"amount": 500, "ageDays": 10}}
    return {"orderId": order_id, **table.get(order_id, {"amount": 0, "ageDays": 0})}


def _read_policy():
    return {"maxAmountUsd": 100, "maxDays": 90}


def _issue_refund(order_id, amount):
    return {"order": order_id, "refunded": amount}


def _write_ledger(case):
    return {"recorded": True, **case}


@ent.node("refundly.decide")
def decide(req):
    run = []
    gate = ent.guard(REGISTRY, record_calls=run)

    gate("parse")
    parsed = _parse(req)
    gate("order_lookup")
    order = _order_lookup(parsed["orderId"])
    gate("read_policy")
    policy = _read_policy()

    within = order["amount"] <= policy["maxAmountUsd"] and order["ageDays"] <= policy["maxDays"]
    decision = "refund" if within else "deny"

    if decision == "refund":
        gate("issue_refund")
        _issue_refund(order["orderId"], order["amount"])

    gate("write_ledger")
    _write_ledger({"order": order["orderId"], "decision": decision})

    return {"decision": decision, "amount": order["amount"], "trajectory": run}
