"""Legacy catalog lookup — unmanaged."""

from __future__ import annotations


def find(request: dict) -> dict:
    return {"sku": request.get("sku"), "price": 0.0}
