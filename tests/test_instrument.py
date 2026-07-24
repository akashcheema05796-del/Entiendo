"""L2 instrumentation tests (Phase 3).

Acceptance (SPEC.md §8, Phase 3): a call through a decorated node produces a span
mapped to the node id. Also verifies the observer never alters behaviour
(Invariant 2): return values pass through, exceptions re-raise, cost meters.
"""

from __future__ import annotations

import pytest

from ent import node, record
from ent.tracing import NODE_ID_ATTR, capture, current_span


def test_span_records_node_id() -> None:
    @node("demo.thing")
    def double(x: int) -> int:
        return x * 2

    with capture() as spans:
        result = double(3)

    assert result == 6  # return value untouched
    assert len(spans) == 1
    span = spans[0]
    assert span.node_id == "demo.thing"
    assert span.as_dict()["attributes"][NODE_ID_ATTR] == "demo.thing"
    assert span.status == "ok"
    assert span.duration_ms >= 0.0


def test_no_capture_records_nothing() -> None:
    @node("demo.quiet")
    def f() -> int:
        return 1

    # Without a capture() block, calling is a plain function call (Invariant 2).
    assert f() == 1
    assert current_span() is None


def test_exception_marks_error_and_reraises() -> None:
    @node("demo.boom")
    def boom() -> None:
        raise ValueError("nope")

    with capture() as spans:
        with pytest.raises(ValueError, match="nope"):
            boom()

    assert spans[0].status == "error"


def test_record_meters_cost_and_tokens() -> None:
    @node("demo.cost")
    def call() -> None:
        record(cost_usd=0.01, tokens=100)
        record(cost_usd=0.02, tokens=50, model="test-model")

    with capture() as spans:
        call()

    span = spans[0]
    assert span.cost_usd == pytest.approx(0.03)
    assert span.tokens == 150
    assert span.attributes["model"] == "test-model"


def test_record_outside_node_is_noop() -> None:
    # Must not raise even when there is no active span.
    record(cost_usd=1.0, tokens=1)


def test_nested_nodes_produce_two_spans() -> None:
    @node("demo.inner")
    def inner() -> int:
        return 2

    @node("demo.outer")
    def outer() -> int:
        return inner() + 1

    with capture() as spans:
        outer()

    ids = {s.node_id for s in spans}
    assert ids == {"demo.inner", "demo.outer"}
