"""Chunk Ranker — claimed by node `retrieval.chunk_ranker`.

Example claimed source for the greenfield demo. The body is illustrative only —
it shows the shape the extractor (Phase 2) will read and the trace binding
(Phase 3) will attribute, not a working ranker.
"""

from __future__ import annotations

import ent

# These intra-project imports are exactly the edges the L1 reconciler verifies:
# retrieval.chunk_ranker -> retrieval.vector_store, and -> llm.gateway. They
# match this node's declared `dependencies.calls`, so `ent extract` reports them
# as verified (declared AND observed) with no drift. Absolute (root-relative)
# imports so the node is also runnable in isolation for tier1/tier2 evals.
from src.gateway.client import complete
from src.vector_store.store import search


@ent.node("retrieval.chunk_ranker")
def rank(request: dict) -> dict:
    """Re-rank candidate chunks for a query.

    Contract (see entiendo.node.yaml + schemas/):
      - len(output.chunks) <= input.k
      - all(c.score >= 0 for c in output.chunks)
    """
    k = request["k"]
    # Illustrative: call the vector store, then the LLM gateway to score.
    hits = search([0.0], top_n=k)  # retrieval.vector_store
    complete("rank these chunks")  # llm.gateway
    ranked = sorted(
        request["candidates"],
        key=lambda c: len(c.get("text", "")),
        reverse=True,
    )[:k]
    return {"chunks": [{"id": c["id"], "score": 1.0} for c in ranked]}
