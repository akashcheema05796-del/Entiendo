"""L1/L3 — Composite node versioning. Pin, diff, revert, replay (SPEC.md §5.4).

STUB. A node's version is a *composite* hash over everything that can change its
behaviour:

    composite = hash(code, prompt, config, model)

Because the version is composite, a single node can be pinned and reverted
without touching anything else — and yesterday's inputs can be replayed against
today's version to see exactly what moved. Model identity is a version dimension
(§7 gap 15): swapping models changes behaviour and must diff.

Phase 2 computes `code`; Phase 3/4 add prompt/config/model capture and history.
"""

from __future__ import annotations

# The dimensions that compose a node version (order is stable for hashing).
VERSION_DIMENSIONS = ("code", "prompt", "config", "model")

# Phase 2+ will add:
#   def compute_version(node) -> Version: ...   # fills code/prompt/config/model
#   def composite(version) -> str: ...          # the hash you pin/diff/revert
