"""Trajectory invariants (v3 Phase D, SPEC §14.2) — reflex checks over the
*sequence* of tool calls an agentic unit makes, not just its final output.

The path can be wrong even when the answer is right: a refund issued before the
order was looked up is a bug regardless of the amount. A trajectory check reads a
recorded run log (a JSONL fixture of tool calls, or spans) and evaluates three
deterministic rules against it:

  - `order`:        ["A before B", ...]  — A must precede B in the sequence
  - `maxSteps`:     N                    — more than N tool calls is RED
  - `registryOnly`: true                 — any tool outside interior.tools is RED

Pure and <1s — no execution, just reasoning over the call list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def calls_from_log(rows: list[dict[str, Any]]) -> list[str]:
    """Extract the ordered tool-call names from a run-log fixture.

    Each row is a tool call: {"tool": "order_lookup", ...} (extra fields ignored).
    Rows without a "tool" key (e.g. a final answer marker) are skipped.
    """
    return [str(r["tool"]) for r in rows if isinstance(r, dict) and r.get("tool")]


def _split_before(constraint: str) -> tuple[str, str] | None:
    """Parse 'A before B' or 'A_before_B' → (A, B)."""
    for sep in (" before ", "_before_"):
        if sep in constraint:
            a, b = constraint.split(sep, 1)
            return a.strip(), b.strip()
    return None


def evaluate(rule: dict[str, Any], calls: list[str], registry: set[str]) -> tuple[bool, str]:
    """Evaluate one trajectory rule against a tool-call sequence.

    `rule` is the tier0 entry ({order, maxSteps, registryOnly}); `calls` is the
    ordered tool names; `registry` is the allowed set (interior.tools names).
    Returns (passed, detail) with real values in the failure detail.
    """
    # registryOnly — no tool outside the declared registry
    if rule.get("registryOnly") and registry:
        for c in calls:
            if c not in registry:
                return False, (f"registryOnly: called {c!r}, which is not in the tool "
                               f"registry {sorted(registry)}")

    # maxSteps — bound on the number of tool calls
    max_steps = rule.get("maxSteps")
    if max_steps is not None and len(calls) > int(max_steps):
        return False, f"maxSteps: {len(calls)} tool calls exceeds maxSteps={max_steps}"

    # order — each 'A before B' ordering constraint
    for constraint in rule.get("order", []) or []:
        parsed = _split_before(constraint)
        if parsed is None:
            return False, f"order: cannot parse constraint {constraint!r} (use 'A before B')"
        a, b = parsed
        if b in calls and a not in calls:
            return False, f"order: {b!r} occurred without the required preceding {a!r} (sequence {calls})"
        if a in calls and b in calls and calls.index(a) > calls.index(b):
            return False, f"order: {a!r} must precede {b!r} but came after it (sequence {calls})"

    return True, f"trajectory ok: {len(calls)} call(s), order + registry + step bound satisfied"
