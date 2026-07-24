"""L2 — Span recording. OTel-compatible, never in the request path (Invariant 2).

Two things happen when an `@ent.node()`-decorated callable runs:

1. If `opentelemetry` is importable, a real OTel span is emitted carrying
   `entiendo.node_id`. If no tracer provider is configured, OTel returns a no-op
   tracer, so this is safe and free in production.
2. If an in-memory `capture()` block is active, a lightweight `Span` is recorded
   for Entiendo's own inspection (tests, demos, the eventual trace lens).

Recording is **opt-in** via `capture()` — there is no unbounded global buffer, so
a long-running app that never calls `capture()` accumulates nothing. Entiendo
observes; it never grows in the hot path.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

# Active in-memory recorder (a list). None = not recording.
_recorder: ContextVar[list["Span"] | None] = ContextVar("ent_recorder", default=None)
# The span currently open on this logical thread, so record() can find it.
_current: ContextVar["Span | None"] = ContextVar("ent_current_span", default=None)

NODE_ID_ATTR = "entiendo.node_id"


@dataclass
class Span:
    """A single node execution. Shaped to map cleanly onto an OTel span."""

    node_id: str
    name: str
    duration_ms: float = 0.0
    status: str = "ok"  # "ok" | "error"
    cost_usd: float | None = None
    tokens: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "cost_usd": self.cost_usd,
            "tokens": self.tokens,
            "attributes": {NODE_ID_ATTR: self.node_id, **self.attributes},
        }


@contextmanager
def capture() -> Iterator[list[Span]]:
    """Record spans emitted within this block into the yielded list."""
    spans: list[Span] = []
    token = _recorder.set(spans)
    try:
        yield spans
    finally:
        _recorder.reset(token)


def current_span() -> Span | None:
    """The span currently open on this logical thread, if any."""
    return _current.get()


def _record(span: Span) -> None:
    buffer = _recorder.get()
    if buffer is not None:
        buffer.append(span)


@contextmanager
def _otel_span(name: str, node_id: str) -> Iterator[None]:
    """Emit a real OTel span if opentelemetry is available, else a no-op."""
    try:
        from opentelemetry import trace
    except Exception:
        yield
        return
    tracer = trace.get_tracer("entiendo")
    with tracer.start_as_current_span(name) as span:
        try:
            span.set_attribute(NODE_ID_ATTR, node_id)
        except Exception:
            pass
        yield
