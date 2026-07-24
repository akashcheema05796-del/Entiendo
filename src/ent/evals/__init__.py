"""L2 — Eval runner. Tiered and cost-aware (SPEC.md §5).

    tier0  deterministic, <1s, free — runs on every edit
    tier1  golden datasets, pre-merge — humanBlessed, minRuns + significance
    tier2  LLM judge, nightly / on demand — expensive

STUB package. Phase 3 builds the tier0 runner first; tier1/tier2 follow.
"""

# Standard verdict vocabulary the health lens consumes (Invariant 7):
#   "green"     — within band
#   "degraded"  — budget burn, not yet a correctness regression
#   "red"       — statistically meaningful regression vs baseline
VERDICTS = ("green", "degraded", "red")
