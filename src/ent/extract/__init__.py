"""Test-case extraction from existing pytest suites (hardening plan, Phase 4).

Static-first for safety (`static_ast.py` never executes repo code),
pytest-collection for coverage (`collect_plugin.py` executes module import
only — sandbox it for untrusted repos), and explicit gaps for everything
else: a case that cannot be represented faithfully becomes a counted
`needs_harness` entry, never a silently wrong one.
"""

from __future__ import annotations

from typing import Any

# One extracted case. `expected` may be None (parametrize rows carry inputs;
# expectations only come from assert patterns or a later human pass).
CASE_FIELDS = ("source_test", "case_id", "inputs", "expected", "marks",
               "extraction_method", "confidence")


def case(source_test: str, case_id: str, inputs: Any, expected: Any,
         marks: list[str], method: str, confidence: str) -> dict[str, Any]:
    return {
        "source_test": source_test,
        "case_id": case_id,
        "inputs": inputs,
        "expected": expected,
        "marks": marks,
        "extraction_method": method,
        "confidence": confidence,
    }
