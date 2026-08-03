"""L2 — Instrumentation. The single piece of code that must live in the app.

`@ent.node("retrieval.chunk_ranker")` binds a callable to a node id and, on every
call, emits a span carrying `entiendo.node_id` (SPEC.md §3, L2). This is what
lets the flow and trace lenses map runtime executions back to the node that
produced them.

Entiendo is a read-only observer and is never in the request path (Invariant 2):
the decorator times the call and re-raises any exception unchanged — it never
swallows errors, never alters return values, and adds no unbounded state. With no
OTel provider configured and no `capture()` active, the overhead is a timer and a
couple of contextvar assignments.
"""

from __future__ import annotations

import functools
import time
from typing import Callable, TypeVar

from . import testing, tracing
from .tracing import Span

F = TypeVar("F", bound=Callable[..., object])


def node(node_id: str, *, span_name: str | None = None) -> Callable[[F], F]:
    """Bind a callable to a node id for trace attribution.

    Args:
        node_id: the manifest `id`, e.g. "retrieval.chunk_ranker".
        span_name: override the emitted span name (defaults to `node_id`, matching
            the manifest's `observability.spanName`).
    """
    name = span_name or node_id

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            # tier0 isolation: a call to a *neighbour* node is served from the
            # fixture stubs (or raises), and never actually runs — no I/O.
            handled, stubbed = testing.intercept(node_id)
            if handled:
                return stubbed

            # the span currently open is this call's caller — record it so a
            # recorded trace carries true caller→callee edges (V1 span verification).
            _parent = tracing._current.get()
            span = Span(node_id=node_id, name=name,
                        parent=_parent.node_id if _parent else None)
            span_token = tracing._current.set(span)
            start = time.perf_counter()
            try:
                with tracing._otel_span(name, node_id):
                    return fn(*args, **kwargs)
            except BaseException:
                span.status = "error"
                raise
            finally:
                span.duration_ms = (time.perf_counter() - start) * 1000.0
                tracing._record(span)
                tracing._current.reset(span_token)

        wrapper.__entiendo_node_id__ = node_id  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def record(*, cost_usd: float | None = None, tokens: int | None = None, **attrs: object) -> None:
    """Attach cost / tokens / attributes to the current node's span — the cost meter.

    Call this from inside a decorated node (e.g. after an LLM call) to meter spend.
    Outside a node it is a safe no-op, so instrumentation code never crashes an app.
    """
    span = tracing.current_span()
    if span is None:
        return
    if cost_usd is not None:
        span.cost_usd = (span.cost_usd or 0.0) + cost_usd
    if tokens is not None:
        span.tokens = (span.tokens or 0) + tokens
    span.attributes.update(attrs)

    # Mirror onto the live OTel span, if any.
    try:
        from opentelemetry import trace

        otel_span = trace.get_current_span()
        if cost_usd is not None:
            otel_span.set_attribute("entiendo.cost_usd", span.cost_usd)
        if tokens is not None:
            otel_span.set_attribute("entiendo.tokens", span.tokens)
    except Exception:
        pass


class RegistryViolation(RuntimeError):
    """An agentic unit called a tool outside its declared `interior.tools` registry."""


def guard(registry, *, record_calls: list | None = None):
    """Return a tool-call guard for an agentic unit (SPEC §14.3).

    `registry` is the allowed tool names (from `interior.tools`). The returned
    callable is invoked with a tool name before dispatch; it raises
    `RegistryViolation` on anything outside the registry, so the border that the
    reconciler enforces at build time also holds at runtime. Still a read-only
    helper — it guards the workload, it is not in the request path unless the app
    chooses to call it.

    Optionally pass `record_calls` (a list) to append each guarded tool name to —
    a run log the trajectory eval can consume.

        gate = ent.guard(["order_lookup", "issue_refund"], record_calls=log)
        gate("order_lookup"); ...            # ok
        gate("delete_everything")            # raises RegistryViolation
    """
    allowed = {str(t) for t in registry}

    def gate(tool_name: str) -> str:
        if tool_name not in allowed:
            raise RegistryViolation(
                f"tool {tool_name!r} is not in the unit's registry {sorted(allowed)}"
            )
        if record_calls is not None:
            record_calls.append(tool_name)
        return tool_name

    return gate
