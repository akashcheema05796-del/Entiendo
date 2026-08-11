"""Oracle-class provenance for golden rows — the tautological-oracle guard.

The test-carving literature (Randoop, EvoSuite, Orstra) is unambiguous:
harvested oracles capture *actual* behaviour, not *expected* behaviour — an
expected value derived from the implementation can only ever agree with it.
"The thing you test against cannot be derived from the thing you're testing."

The counter is provenance. Every golden row may carry an `oracleClass`:

  contract-derivable      the expected value follows from the contract / spec
                          alone — a human could produce it without running the
                          code. Admissible ground truth.
  implementation-derived  captured from the code's own output (trace harvest,
                          snapshot, regression carve). Quarantined: blessing a
                          dataset containing these requires the explicit
                          `--accept-implementation-derived` flag, so accepting
                          actual-as-expected is a conscious human choice.
  (absent / other)        unknown — legacy rows. Counted and shown at bless
                          time, never silently promoted to either class.

This module is pure classification; `ent bless` applies the teeth.
"""

from __future__ import annotations

from typing import Any, Iterable

CONTRACT_DERIVABLE = "contract-derivable"
IMPLEMENTATION_DERIVED = "implementation-derived"
UNKNOWN = "unknown"
CLASSES = (CONTRACT_DERIVABLE, IMPLEMENTATION_DERIVED)


def row_class(row: dict[str, Any]) -> str:
    """A row's oracle class; anything unrecognised is 'unknown', never an error
    (legacy datasets predate the field)."""
    value = row.get("oracleClass")
    return value if value in CLASSES else UNKNOWN


def census(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {CONTRACT_DERIVABLE: 0, IMPLEMENTATION_DERIVED: 0, UNKNOWN: 0}
    for row in rows:
        counts[row_class(row)] += 1
    return counts


def quarantined(rows: Iterable[dict[str, Any]]) -> list[str]:
    """Names of the rows whose expected values came from the implementation."""
    return [str(row.get("name", f"row{i}"))
            for i, row in enumerate(rows)
            if row_class(row) == IMPLEMENTATION_DERIVED]


def describe(counts: dict[str, int]) -> str:
    parts = [f"{n} {cls}" for cls, n in counts.items() if n]
    return ", ".join(parts) if parts else "empty dataset"
