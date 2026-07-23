"""L1 — Extractor / reconciler. The real anti-drift mechanism.

STUB. Phase 2 fills this in. It statically analyses each node's claimed files,
derives the *actual* imports/calls/reads/writes, and reconciles them against the
`dependencies` declared in the manifest. Divergence is a build failure, not a
warning (Invariant 5).

Outputs (both GENERATED — never hand-edited, SPEC.md §12):
  - entiendo/graph.json     the node topology + verified edges
  - entiendo/coverage.json  claimed vs unclaimed files; coverage headline number
"""

from __future__ import annotations

GRAPH_ARTIFACT = "entiendo/graph.json"
COVERAGE_ARTIFACT = "entiendo/coverage.json"

# Phase 2 will add:
#   def extract(root) -> Graph: ...          # build the verified topology
#   def reconcile(graph) -> list[Drift]: ... # declared vs actual; [] means clean
#   def coverage(root) -> Coverage: ...      # every file claimed once, or unclaimed
