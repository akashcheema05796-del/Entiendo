"""Chunk Ranker — claimed by node `retrieval.chunk_ranker`.

Example claimed source for the greenfield demo. The body is illustrative only —
it shows the shape the extractor (Phase 2) will read and the trace binding
(Phase 3) will attribute, not a working ranker.
"""

from __future__ import annotations

import ent


@ent.node("retrieval.chunk_ranker")
def rank(request: dict) -> dict:
    """Re-rank candidate chunks for a query.

    Contract (see entiendo.node.yaml + schemas/):
      - len(output.chunks) <= input.k
      - all(c.score >= 0 for c in output.chunks)
    """
    k = request["k"]
    # Illustrative: real logic would call retrieval.vector_store + llm.gateway
    # and read from state.doc_index — exactly the edges the reconciler verifies.
    ranked = sorted(
        request["candidates"],
        key=lambda c: len(c.get("text", "")),
        reverse=True,
    )[:k]
    return {"chunks": [{"id": c["id"], "score": 1.0} for c in ranked]}
