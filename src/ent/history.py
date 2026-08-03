"""L3 — History store. Append-only versions + eval results (SPEC.md §3, L3).

Boring, inspectable storage: a single append-only JSONL log at
entiendo/history/events.jsonl. History is never rewritten, only extended — the
tool must be trivially recoverable (SPEC.md §12). Each line is one event:

    {"seq": 0, "kind": "version", "nodeId": "...", "composite": "...",
     "version": {...}, "commit": "abc1234", "ts": "..."}
    {"seq": 1, "kind": "eval", "nodeId": "...", "verdict": "green",
     "tier": 0, "commit": "abc1234", "ts": "..."}

Version events are deduplicated: a version is appended only when a node's
composite differs from the last recorded one, so the timeline shows *changes*,
not every snapshot. This is what makes "a node's version change is visible on the
timeline within one commit" true.

Node versions & manifests properly live in git (content-addressed); this log is
the queryable index over them and over eval results.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

HISTORY_DIR = "entiendo/history"
BASELINES_DIR = "entiendo/baselines"
EVENTS_FILE = "entiendo/history/events.jsonl"


def _events_path(root: Path) -> Path:
    return Path(root) / EVENTS_FILE


def read_events(root: Path) -> list[dict[str, Any]]:
    """All history events in append order."""
    path = _events_path(root)
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _append(root: Path, event: dict[str, Any]) -> dict[str, Any]:
    path = _events_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    seq = len(read_events(root))
    event = {"seq": seq, **event}
    with path.open("a") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def record(root: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append an arbitrary event to the log (e.g. proposal approved/rejected)."""
    return _append(root, event)


def latest_version(root: Path, node_id: str) -> dict[str, Any] | None:
    """The most recent version event payload for a node, or None."""
    latest = None
    for e in read_events(root):
        if e["kind"] == "version" and e["nodeId"] == node_id:
            latest = e
    return latest


def append_version(
    root: Path,
    node_id: str,
    version: dict[str, Any],
    *,
    commit: str | None = None,
    ts: str | None = None,
) -> dict[str, Any] | None:
    """Append a version event iff the composite changed. Returns the event or None."""
    prev = latest_version(root, node_id)
    if prev is not None and prev.get("composite") == version.get("composite"):
        return None
    return _append(
        root,
        {
            "kind": "version",
            "nodeId": node_id,
            "composite": version.get("composite"),
            "version": version,
            "commit": commit,
            "ts": ts,
        },
    )


def append_eval(
    root: Path,
    node_id: str,
    verdict: str,
    tier: int,
    *,
    commit: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Append an eval-result event."""
    return _append(
        root,
        {
            "kind": "eval",
            "nodeId": node_id,
            "verdict": verdict,
            "tier": tier,
            "commit": commit,
            "ts": ts,
        },
    )


def timeline(root: Path, node_id: str | None = None) -> list[dict[str, Any]]:
    """Events for one node (or all), in order. The timeline lens reads this."""
    events = read_events(root)
    if node_id is None:
        return events
    return [e for e in events if e.get("nodeId") == node_id]


def append_trace(
    root: Path,
    hops: list[dict[str, Any]],
    *,
    trace_id: str,
    commit: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Append a trace event — one request's hops (node, latency, status, cost).

    The trace lens (lens 3) reads these to answer 'what happened to *this*
    request?' with latency per hop.
    """
    total = round(max((h.get("duration_ms", 0.0) for h in hops), default=0.0), 3)
    return _append(
        root,
        {
            "kind": "trace",
            "traceId": trace_id,
            "hops": hops,
            "totalMs": total,
            "commit": commit,
            "ts": ts,
        },
    )


def traces(root: Path) -> list[dict[str, Any]]:
    """All recorded trace events, in order."""
    return [e for e in read_events(root) if e.get("kind") == "trace"]


@contextmanager
def capture_trace(
    root: Path,
    *,
    trace_id: str,
    commit: str | None = None,
    ts: str | None = None,
) -> Iterator[list[Any]]:
    """Capture spans from `@ent.node()` calls in this block and record them.

    Read-only: this only observes and persists — it never alters the wrapped
    calls (Invariant 2). Usage:

        with history.capture_trace(root, trace_id="req-1"):
            handle_request(...)
    """
    from . import tracing  # L3 may depend on L2

    with tracing.capture() as spans:
        yield spans
    composites = _composites_for(root, {s.node_id for s in spans})
    hops = [
        {
            "node": s.node_id,
            "duration_ms": round(s.duration_ms, 3),
            "status": s.status,
            "cost_usd": s.cost_usd,
            "tokens": s.tokens,
            # V1: caller + the caller/callee composite at observation time, so the
            # reconciler can verify edges from spans and expire them on drift.
            "parent": s.parent,
            "compositeVersion": composites.get(s.node_id),
        }
        for s in spans
    ]
    append_trace(root, hops, trace_id=trace_id, commit=commit, ts=ts)


def _composites_for(root: Path, node_ids: set[str]) -> dict[str, str | None]:
    """Composite version of each node at capture time (best-effort, never raises)."""
    out: dict[str, str | None] = {}
    try:
        from .manifest import find_node
        from .version import compute_version
    except ModuleNotFoundError:
        return out
    for nid in node_ids:
        try:
            node = find_node(root, nid)
            out[nid] = compute_version(node, root)["composite"] if node else None
        except Exception:
            out[nid] = None
    return out
