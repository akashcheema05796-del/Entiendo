"""A unit that is SUPPOSED to fail its invariant.

ent.evalkit's eval uses it to prove the runner can return RED, not just GREEN —
otherwise a mutation that rubber-stamps everything would pass unnoticed.
"""


def check(payload):
    return {"ok": False}
