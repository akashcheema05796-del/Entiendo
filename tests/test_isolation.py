"""tier0 isolation / stubbing (Phase 7 §2).

I/O is modelled as calls through `@ent.node()` neighbours: during tier0 those
are served from the fixture stubs, and any unstubbed call is an I/O violation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ent import node, testing


@node("dep.x")
def dep_x(req: dict) -> dict:
    return {"real_io": True}  # in real life this would hit the network


@node("nut.single")
def nut_single(req: dict) -> dict:
    return dep_x({})  # one neighbour call


@node("nut.double")
def nut_double(req: dict) -> dict:
    dep_x({})
    dep_x({})
    return {"ok": True}


@node("nut.pure")
def nut_pure(req: dict) -> dict:
    return {"n": req["n"] * 2}  # no neighbour calls


def test_stubbed_dependency_is_served() -> None:
    target = SimpleNamespace(id="nut.single")
    row = {"deps": {"dep.x": [{"stubbed": True}]}}
    with testing.stub(target, row):
        out = nut_single({})
    assert out == {"stubbed": True}  # dep_x's real body never ran


def test_unstubbed_dependency_is_io_violation() -> None:
    target = SimpleNamespace(id="nut.single")
    with testing.stub(target, {"deps": {}}):
        with pytest.raises(testing.Tier0IOViolation) as exc:
            nut_single({})
    assert "dep.x" in str(exc.value)


def test_queue_exhausted_when_called_too_often() -> None:
    target = SimpleNamespace(id="nut.double")
    row = {"deps": {"dep.x": [{"one": 1}]}}  # only one stub, node calls twice
    with testing.stub(target, row):
        with pytest.raises(testing.Tier0QueueExhausted):
            nut_double({})


def test_pure_node_runs_without_stubs() -> None:
    target = SimpleNamespace(id="nut.pure")
    with testing.stub(target, {}):
        assert nut_pure({"n": 21}) == {"n": 42}


def test_outside_tier0_calls_run_normally() -> None:
    # No stub context: the decorated neighbour runs its real body.
    assert nut_single({}) == {"real_io": True}
