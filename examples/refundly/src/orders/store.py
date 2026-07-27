"""refundly.orders — the order ledger (state). The target of order_lookup."""

_ORDERS = {"o1": {"amount": 42}, "o2": {"amount": 42}}


def lookup(order_id):
    return _ORDERS.get(order_id, {"amount": 0})
