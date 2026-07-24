"""Vector Store — claimed by node `retrieval.vector_store`.

Illustrative claimed source for the greenfield demo.
"""

from __future__ import annotations

import ent


@ent.node("retrieval.vector_store")
def search(query_vec: list[float], top_n: int = 20) -> dict:
    """Return the top-N nearest document chunks. Reads state.doc_index."""
    # Illustrative only.
    return {"hits": []}
