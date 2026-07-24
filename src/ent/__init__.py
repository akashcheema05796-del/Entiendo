"""Entiendo — the node is the unit of work.

Build-time instrumentation, a generated system map, and a scoped editing loop.
See SPEC.md for the full specification.

Public surface:
    ent.node     — the @ent.node("<id>") instrumentation decorator (L2)
    ent.record   — meter cost / tokens onto the current node's span (L2)

Everything else is internal and moves as the phases land (L0 → L5).
"""

from __future__ import annotations

__version__ = "0.1.0"
__api_version__ = "entiendo/v1"

from .instrument import node, record

__all__ = ["node", "record", "__version__", "__api_version__"]
