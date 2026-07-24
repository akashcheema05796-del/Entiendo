"""L3 — History store. Append-only versions + eval results + traces.

STUB. Phase 4 implements the storage split (SPEC.md §3, L3 detail):

  - Node versions & manifests → git (content-addressed, free history)
  - Eval results & budgets     → time-series (DuckDB/Parquet is enough to start)
  - Traces                     → span store (OTel-compatible), sampled
  - Graph snapshots            → entiendo/graph.json per commit

Prefer boring, inspectable storage over a database service — the tool must be
trivially recoverable (SPEC.md §12). The log is append-only: history is never
rewritten, only extended.
"""

from __future__ import annotations

HISTORY_DIR = "entiendo/history"
BASELINES_DIR = "entiendo/baselines"

# Phase 4 will add:
#   def append_version(node, version) -> None: ...
#   def append_eval(node, result) -> None: ...
#   def timeline(node_id) -> list[Event]: ...   # code + schema + config on one axis
