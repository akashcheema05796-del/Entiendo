"""L2 — Instrumentation. The single piece of code that must live in the app.

STUB. The real decorator (Phase 3) emits an OpenTelemetry span carrying
`entiendo.node_id` so the flow and trace lenses can bind runtime executions back
to the node that produced them (SPEC.md §3, L2).

Until then this is a transparent pass-through: importing and decorating with
`@ent.node("...")` is safe and does nothing but run your function. Entiendo is a
read-only observer and is never in the request path (Invariant 2) — so the
no-op default is the *correct* failure mode, not a temporary hack.
"""

from __future__ import annotations

import functools
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., object])


def node(node_id: str) -> Callable[[F], F]:
    """Bind a callable to a node id for trace attribution.

    Args:
        node_id: the manifest `id`, e.g. "retrieval.chunk_ranker".

    Returns:
        A decorator. Currently a pass-through; Phase 3 wires the OTel span with
        `entiendo.node_id = node_id`, plus latency and cost capture.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            # Phase 3: open span, set entiendo.node_id, record latency/cost.
            return fn(*args, **kwargs)

        # Stash the binding so later phases (and tests) can discover it without
        # a live tracer installed.
        wrapper.__entiendo_node_id__ = node_id  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
