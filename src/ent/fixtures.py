"""Propose tier0 smoke-fixture skeletons from recorded traces (gap analysis §3).

Fixture authoring is the birth tax on a unit: you hand-write each row and, for a
unit with neighbours, the dependency stubs that keep tier0 isolated. Recorded
traces already know a lot of that — which units ran, in what order, with what
status/latency/cost — so this proposes a *skeleton* per trace that exercised a
unit and lets the human fill the rest.

Honest about the gap: spans carry node id + timing + status + cost, **not request
payloads** (Invariant 2 keeps the observer out of the data path). So `input` is a
placeholder the human completes; what the trace *can* give — pre-wired dep stubs,
a name tied to a real request, and error cases worth covering — it does.

This mirrors retrofit: propose, never overwrite. The real fixture is never
touched; proposals land under `entiendo/proposals/fixtures/` for review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import history
from .manifest import find_node

# Dependency buckets whose neighbours get stubbed for tier0 isolation.
_STUBBED_DEPS = ("calls", "reads")

INPUT_PLACEHOLDER = "TODO: reconstruct the request payload for this trace"


@dataclass(frozen=True)
class FixtureProposal:
    fixture: dict[str, Any]        # the smoke-fixture row (name, input, deps)
    source_trace: str              # the traceId it was derived from
    observed: dict[str, Any]       # status / durationMs / costUsd from the hop
    notes: list[str] = field(default_factory=list)


def _stub_targets(node: Any, trace_nodes: set[str]) -> list[str]:
    """Declared call/read neighbours that actually appear in the trace."""
    deps = (node.raw.get("dependencies", {}) or {}) if node else {}
    targets: list[str] = []
    for bucket in _STUBBED_DEPS:
        for target in deps.get(bucket) or []:
            if target in trace_nodes and target not in targets:
                targets.append(target)
    return targets


def propose_from_traces(root: Path, unit_id: str) -> list[FixtureProposal]:
    """One skeleton smoke fixture per recorded trace that exercised `unit_id`."""
    root = Path(root)
    node = find_node(root, unit_id)
    proposals: list[FixtureProposal] = []
    seen_names: set[str] = set()

    for trace in history.traces(root):
        hops = trace.get("hops", []) or []
        mine = next((h for h in hops if h.get("node") == unit_id), None)
        if mine is None:
            continue

        trace_id = trace.get("traceId") or f"trace{len(proposals)}"
        name = f"from-{trace_id}"
        if name in seen_names:
            name = f"{name}-{len(proposals)}"
        seen_names.add(name)

        trace_nodes = {h.get("node") for h in hops}
        stub_targets = _stub_targets(node, trace_nodes)
        deps = {t: [{}] for t in stub_targets}          # one placeholder stub each

        fixture: dict[str, Any] = {"name": name, "input": {"_": INPUT_PLACEHOLDER}}
        if deps:
            fixture["deps"] = deps

        notes: list[str] = []
        status = mine.get("status")
        if status and status != "ok":
            notes.append(f"trace status was '{status}' — an error case worth covering")
        if stub_targets:
            notes.append(f"pre-wired stubs for {', '.join(stub_targets)} — fill the return values")
        if node is None:
            notes.append(f"no manifest found for '{unit_id}' — dep stubs not scaffolded")

        proposals.append(FixtureProposal(
            fixture=fixture,
            source_trace=trace_id,
            observed={"status": status,
                      "durationMs": mine.get("duration_ms"),
                      "costUsd": mine.get("cost_usd")},
            notes=notes,
        ))
    return proposals


def proposal_path(root: Path, unit_id: str) -> Path:
    return Path(root) / "entiendo" / "proposals" / "fixtures" / f"{unit_id}.smoke.jsonl"


def write_proposals(root: Path, unit_id: str, proposals: list[FixtureProposal]) -> Path:
    """Write the skeletons to a proposal file (never the real fixture)."""
    import json

    path = proposal_path(root, unit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(p.fixture) + "\n" for p in proposals))
    return path
