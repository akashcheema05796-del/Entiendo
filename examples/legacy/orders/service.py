"""An unmanaged legacy module — no entiendo.node.yaml anywhere in this tree.
`ent retrofit examples/legacy` infers a node from it and proposes a manifest.
"""

from __future__ import annotations

from catalog.lookup import find
from ledger.write import record


def place_order(request: dict) -> dict:
    """Place an order: look up the item, then record it to the ledger."""
    item = find({"sku": request["sku"]})
    record({"order": request, "item": item})
    return {"ok": True, "item": item}
