"""Legacy ledger writer — unmanaged."""

from __future__ import annotations


def record(request: dict) -> dict:
    return {"written": True}
