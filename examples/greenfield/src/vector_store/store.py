"""Vector Store — claimed by node `retrieval.vector_store`.

Illustrative claimed source for the greenfield demo.
"""

from __future__ import annotations

import ent


@ent.node("retrieval.vector_store")
def search(request: dict) -> dict:
    """Return the top-N nearest document chunks. Reads state.doc_index.

    One dict in, one dict out (Phase 7 §1.1): {query_vec, top_n} -> {hits}.
    """
    top_n = request.get("top_n", 20)
    # Illustrative only — a real store reads state.doc_index.
    return {"hits": []}
