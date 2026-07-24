"""Isolation for tier0 execution (Phase 7 §2).

tier0 must stay deterministic, sub-second, and free — but real nodes call LLMs,
vector stores, and databases. The model: **I/O happens through `@ent.node()`
decorated neighbours**, so during tier0 we intercept those calls and serve canned
responses from the fixture, and treat any *unstubbed* neighbour call as I/O.

    with testing.stub(node, row):
        output = entrypoint(row["input"])

Two loud, distinguishable failures:
  - **Unstubbed dependency called** → `Tier0IOViolation`, naming the node_id.
    Usually means the manifest's `dependencies` block is wrong.
  - **Queue exhausted** → the node called a dependency more times than the
    fixture anticipated (retry loop, N+1). Reports the count.

Pure nodes (no `dependencies.calls`) supply no stubs and just run.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

_tier0: ContextVar["Tier0Context | None"] = ContextVar("ent_tier0", default=None)


class Tier0IOViolation(RuntimeError):
    """A tier0 node reached an unstubbed dependency — i.e. attempted I/O."""


class Tier0QueueExhausted(RuntimeError):
    """A tier0 node called a stubbed dependency more times than the fixture allows."""


@dataclass
class Tier0Context:
    target: str
    stub_queues: dict[str, list[Any]]
    calls: dict[str, int] = field(default_factory=dict)


@contextmanager
def stub(node: Any, row: dict[str, Any]) -> Iterator[Tier0Context]:
    """Install the fixture's dependency stubs for one tier0 execution."""
    deps = row.get("deps") or {}
    ctx = Tier0Context(
        target=node.id,
        stub_queues={dep_id: list(responses) for dep_id, responses in deps.items()},
    )
    token = _tier0.set(ctx)
    try:
        yield ctx
    finally:
        _tier0.reset(token)


def intercept(node_id: str) -> tuple[bool, Any]:
    """Called by the `@ent.node()` wrapper.

    Returns (handled, value): if handled, the wrapper returns `value` without
    running the function (no I/O). Raises on an unstubbed or over-called dep.
    Outside a tier0 context, or for the node under test, returns (False, None).
    """
    ctx = _tier0.get()
    if ctx is None or node_id == ctx.target:
        return False, None

    ctx.calls[node_id] = ctx.calls.get(node_id, 0) + 1
    if node_id in ctx.stub_queues:
        queue = ctx.stub_queues[node_id]
        if queue:
            return True, queue.pop(0)
        raise Tier0QueueExhausted(
            f"{node_id} called {ctx.calls[node_id]} time(s) — more than the fixture stubs"
        )
    raise Tier0IOViolation(node_id)
