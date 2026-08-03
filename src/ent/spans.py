"""Span → edge observation (V1). The runtime half of "verified, not inferred".

Static import analysis (the extractor's default) proves an edge *can* fire.
Recorded spans prove an edge *did* fire. This reads recorded traces — flat hop
lists where each hop carries its `parent` node id and its `compositeVersion` at
observation time (see `history.capture_trace`) — and aggregates the observed
caller→callee edges, so the reconciler can flip a declared edge to `verified`
with a real runtime source.

`callerComposite` is the caller node's composite version when the edge was
observed; the reconciler compares it to the caller's *current* composite and lets
a stale observation expire (verification is per (edge, caller composite version),
so it can't rot silently — plan V1.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import history


@dataclass
class ObservedEdge:
    frm: str
    to: str
    observationCount: int = 0
    lastVerifiedAt: str | None = None
    callerComposite: str | None = None


def observe(trace_events: list[dict[str, Any]]) -> dict[tuple[str, str], ObservedEdge]:
    """Aggregate caller→callee edges from recorded trace hops.

    An edge is `(hop.parent, hop.node)` — a real parent/child span pair. Hops
    with no parent (a top-level entry) contribute no edge.
    """
    agg: dict[tuple[str, str], ObservedEdge] = {}
    for trace in trace_events:
        hops = trace.get("hops", []) or []
        composite_by_node = {h.get("node"): h.get("compositeVersion") for h in hops}
        ts = trace.get("ts")
        for hop in hops:
            parent = hop.get("parent")
            node = hop.get("node")
            if not parent or not node:
                continue
            key = (parent, node)
            obs = agg.get(key)
            if obs is None:
                obs = ObservedEdge(frm=parent, to=node)
                agg[key] = obs
            obs.observationCount += 1
            obs.callerComposite = composite_by_node.get(parent)
            if ts and (obs.lastVerifiedAt is None or ts > obs.lastVerifiedAt):
                obs.lastVerifiedAt = ts
    return agg


def observe_root(root: Path) -> dict[tuple[str, str], ObservedEdge]:
    """Observed edges from the project's own recorded history."""
    return observe(history.traces(Path(root)))


def observe_path(path: Path) -> dict[tuple[str, str], ObservedEdge]:
    """Observed edges from a span source: an events.jsonl (trace events) file."""
    import json

    path = Path(path)
    traces: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("kind") == "trace" or "hops" in event:
                traces.append(event)
    return observe(traces)
