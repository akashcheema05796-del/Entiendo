"""L2 — tier0 eval runner.

STUB. Phase 3 implements the deterministic tier0 checks that run on every edit:

  - schema_validation  input/output conform to the node contract's schemas
  - invariant_check    every `contract.invariants` expression holds
  - smoke              the node runs clean over a small fixture (jsonl)

Non-determinism is handled at tier1, not here: tier0 checks must themselves be
deterministic and sub-second (SPEC.md §5.1). A verdict is judged against the
baseline with a significance threshold, never a raw score (Invariant 7).
"""

from __future__ import annotations

# Phase 3 will add:
#   def run_tier0(node) -> Verdict: ...
#   def run_tier1(node) -> Verdict: ...   # minRuns replays; significance gate
#   def run_tier2(node) -> Verdict: ...   # llm judge over rubric
