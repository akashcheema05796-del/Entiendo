"""Harnesses for Entiendo's own units.

Nine units were permanently UNTESTED because tier0 calls `entrypoint(input)`
with exactly one argument, and their real entrypoints take `(node, root)`,
`(root, node_id)`, or nothing at all. That was a hole in the map, not a fact
about the code: `contract.harness` lets a unit say how a fixture row becomes a
call.

Each function here is handed `(row, ctx)` — `ctx.entrypoint` is the callable
the manifest declares, `ctx.root` is the project root, `ctx.node` is the unit.
The declared entrypoint stays the single source of truth for what runs; the
harness only adapts arguments and returns what invariants then judge.

This is test scaffolding: it lives under evals/, is NOT claimed by any unit,
and so never enters a composite fingerprint.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _fixture_project(ctx) -> Path:
    """The tiny managed project the self-host units run against."""
    return Path(ctx.root) / "evals" / "fixtures" / "miniproj"


def _fixture_node(ctx, node_id: str = "mini.hello"):
    from ent.manifest import find_node
    proj = _fixture_project(ctx)
    node = find_node(proj, node_id)
    if node is None:                      # a broken fixture must be loud
        raise RuntimeError(f"fixture project has no unit '{node_id}'")
    return node


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #

def compute_version(row, ctx):
    """version.compute_version(node, root) — fingerprint the fixture unit."""
    proj = _fixture_project(ctx)
    return ctx.entrypoint(_fixture_node(ctx, row["input"]["unit"]), proj)


def run_tier0(row, ctx):
    """runner.run_tier0(node, root) — evaluate BOTH fixture units.

    Deliberately a different project: pointing the runner at its own unit would
    recurse. And deliberately two units — a passing one and one that fails its
    invariant on purpose — because "returns GREEN" alone is satisfied by a
    runner that rubber-stamps everything. The RED case is what makes this eval
    able to fail.

    Self-reference is still a real limit here: a mutation that breaks fixture
    LOADING degrades this unit's own eval to UNTESTED rather than RED. UNTESTED
    is not a pass, so the regression still surfaces — but it surfaces as a hole
    rather than a failure.
    """
    proj = _fixture_project(ctx)
    good = ctx.entrypoint(_fixture_node(ctx, row["input"]["good"]), proj)
    bad = ctx.entrypoint(_fixture_node(ctx, row["input"]["bad"]), proj)
    return {"good": good.verdict, "bad": bad.verdict, "tier": good.tier}


# --------------------------------------------------------------------------- #
# quality / runtime state
# --------------------------------------------------------------------------- #

def read_baseline(row, ctx):
    """baselines.read_baseline(root, node_id) — round-trip through a scratch
    project, so the read is judged against a baseline we know we wrote."""
    from ent import baselines
    data = row["input"]["baseline"]
    with tempfile.TemporaryDirectory() as tmp:
        baselines.write_baseline(Path(tmp), row["input"]["unit"], data)
        return ctx.entrypoint(Path(tmp), row["input"]["unit"])


def record_event(row, ctx):
    """history.record(root, event) — append into a scratch project. Never the
    real ledger: an eval must not write to the flight recorder."""
    with tempfile.TemporaryDirectory() as tmp:
        return ctx.entrypoint(Path(tmp), dict(row["input"]["event"]))


def instrument_node(row, ctx):
    """instrument.node(id) — the decorator that lives inside the observed app.

    Proves Invariant 2 the only way that counts: decorate a real function, call
    it, and check the return value came back UNALTERED while a span was still
    emitted.
    """
    from ent import tracing
    decorator = ctx.entrypoint(row["input"]["unit"])

    @decorator
    def subject(x):
        return x * 2

    with tracing.capture() as spans:
        result = subject(row["input"]["value"])
    return {"result": result,
            "spans": len([s for s in spans if s.node_id == row["input"]["unit"]])}


def evaluate_trajectory(row, ctx):
    """trajectory.evaluate(rule, calls, registry) — judge a tool-call order."""
    ok, detail = ctx.entrypoint(row["input"]["rule"],
                                list(row["input"]["calls"]),
                                set(row["input"]["registry"]))
    return {"ok": ok, "detail": detail}


# --------------------------------------------------------------------------- #
# agents / distribution
# --------------------------------------------------------------------------- #

def check_boundary(row, ctx):
    """editloop.check_boundary(node, paths, root) — the law this whole system
    rests on: a write outside a unit's claims is refused."""
    proj = _fixture_project(ctx)
    return ctx.entrypoint(_fixture_node(ctx, row["input"]["unit"]),
                          list(row["input"]["paths"]), proj)


def resolve_version(row, ctx):
    """ent._resolve_version() — takes no arguments at all.

    Guards the drift that shipped a 0.2.0 wheel reporting 0.1.0.
    """
    return {"version": ctx.entrypoint()}


def managed_root(row, ctx):
    """enforce_claims._managed_root(path) — does the hook find the project a
    file belongs to? Returns a name so the invariant can be a plain string
    check rather than a Path comparison."""
    target = _fixture_project(ctx) / row["input"]["path"]
    found = ctx.entrypoint(target)
    return {"root": "" if found is None else Path(found).name}
