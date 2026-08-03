"""L4 — Render surface. One topology, six lenses (SPEC.md §4). Phase 4 ships
lenses 1 (structure), 4 (health), 5 (timeline).

Read-only observer, never in the request path (Invariant 2): the view is built by
reading manifests + graph + history and by running the same deterministic tier0
evals `ent eval` runs — so the **health colour always matches `ent eval` output**
by construction. Output is a single self-contained HTML file (inline CSS/JS, no
external requests), so it is trivially serveable and inspectable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import gitinfo, history, verdicts
from .evals.runner import run_tier0
from .extractor import extract
from .manifest import Node, discover, load
from .version import VERSION_DIMENSIONS, compute_version


def build_view(root: Path) -> dict[str, Any]:
    """Assemble the render model: nodes + edges + health + versions + timelines."""
    root = Path(root)
    nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    # The Universe verifies edges from the project's own recorded spans (V1) —
    # so a declared edge a runtime trace confirmed renders solid, not tentative.
    from . import spans
    result = extract(root, spans=spans.observe_root(root))

    # Trace data first (H0.1): the UI plays traces back and shows measured budgets.
    trace_events = history.traces(root)
    traffic: dict[str, int] = {}
    for trace in trace_events:
        for hop in trace.get("hops", []):
            traffic[hop["node"]] = traffic.get(hop["node"], 0) + 1
    measured = _measured_budgets(trace_events)

    by_id = {n.id: n for n in nodes}
    node_views = []
    executable = 0
    for gnode in result.graph["nodes"]:
        node = by_id.get(gnode["id"])
        result0 = run_tier0(node, root) if node else None
        health = result0.verdict if result0 else verdicts.ERROR
        if health != verdicts.UNTESTED:
            executable += 1
        version = compute_version(node, root) if node else {}
        raw = node.raw if node else {}
        contract = raw.get("contract", {}) or {}
        declared_budgets = raw.get("budgets", {}) or {}
        view = {
            **gnode, "health": health,
            "healthColour": verdicts.colour(health), "version": version,
            # dossier, logic-first: description (paragraph) → task (line) → contract
            "description": raw.get("description"),
            "task": raw.get("task") or raw.get("name") or gnode["id"],
            "invariants": list(contract.get("invariants", []) or []),
            # budgets: declared + measured-from-traces (H0.1 / audit finding 2)
            "budgets": {**declared_budgets, "measured": measured.get(gnode["id"])},
            "trajectoryVerdict": _trajectory_verdict(result0),
        }
        interior = raw.get("interior")
        if interior:                         # agentic units only (audit finding 1)
            traj = next((e for e in (raw.get("evals", {}).get("tier0", []) or [])
                         if e.get("type") == "trajectory"), None)
            # surface whether the registry is enforced (orbit ring dashes if not) — H4
            view["interior"] = {**interior,
                                "registryOnly": bool(traj.get("registryOnly")) if traj else None}
        node_views.append(view)

    timelines = {n.id: history.timeline(root, n.id) for n in nodes}
    _annotate_fingerprint_deltas(timelines)
    commits = _commit_axis(timelines)

    return {
        "apiVersion": "entiendo/v1",
        "commit": gitinfo.short_commit(root),
        "coverage": result.coverage,
        "nodes": sorted(node_views, key=lambda n: n["id"]),
        "edges": result.graph["edges"],
        "reconciled": result.ok,
        "executable": executable,
        "nodeCount": len(node_views),
        "timelines": timelines,
        "traces": [_trace_view(t) for t in trace_events],
        "traffic": traffic,
        "commits": commits,          # the Timeline scrubber's axis (H3)
    }


def _commit_axis(timelines: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Ordered distinct commits from version events — the Timeline scrub axis.

    Precomputed here so the scrubber reads fingerprint-per-commit; it never
    re-checks-out (PLAN_v4 risk note). Each unit's fingerprint at a scrubbed
    commit is the last version tick at or before it (derived client-side).
    """
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for events in timelines.values():
        for e in events:
            if e.get("kind") != "version":
                continue
            c = e.get("commit")
            if c is None:
                continue
            if c not in seen:
                seen[c] = {"commit": c, "ts": e.get("ts")}
                order.append(c)
    return [seen[c] for c in order]


def _percentile(xs: list[float], p: int) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _measured_budgets(traces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-unit measured latency/cost derived from recorded trace hops (H0.1)."""
    agg: dict[str, dict[str, list[float]]] = {}
    for tr in traces:
        for hop in tr.get("hops", []):
            nid = hop.get("node")
            if nid is None:
                continue
            a = agg.setdefault(nid, {"lat": [], "cost": []})
            if hop.get("duration_ms") is not None:
                a["lat"].append(hop["duration_ms"])
            if hop.get("cost_usd") is not None:
                a["cost"].append(hop["cost_usd"])
    out: dict[str, dict[str, Any]] = {}
    for nid, a in agg.items():
        lat, cost = a["lat"], a["cost"]
        out[nid] = {
            "calls": len(lat),
            "avgLatencyMs": round(sum(lat) / len(lat), 3) if lat else None,
            "p95LatencyMs": round(_percentile(lat, 95), 3) if lat else None,
            "avgCostUsd": round(sum(cost) / len(cost), 6) if cost else None,
            "totalCostUsd": round(sum(cost), 6) if cost else None,
        }
    return out


def _trajectory_verdict(result0: Any) -> dict[str, Any] | None:
    """The last trajectory-eval outcome + the rule detail on RED (H0.1)."""
    if result0 is None:
        return None
    traj = [c for c in result0.checks if c.type == "trajectory"]
    if not traj:
        return None
    failed = next((c for c in traj if c.status == "fail"), None)
    if failed is not None:
        return {"verdict": verdicts.RED, "failedRule": failed.detail}
    return {"verdict": verdicts.GREEN, "detail": traj[-1].detail}


def _trace_view(t: dict[str, Any]) -> dict[str, Any]:
    """Expose a trace for playback: id, ordered hops, total latency + cost (H0.1)."""
    hops = t.get("hops", [])
    return {
        "id": t.get("traceId"),
        "hops": hops,
        "totalMs": t.get("totalMs"),
        "totalCostUsd": round(sum(h.get("cost_usd") or 0.0 for h in hops), 6),
        "commit": t.get("commit"),
        "ts": t.get("ts"),
    }


def _annotate_fingerprint_deltas(timelines: dict[str, list[dict[str, Any]]]) -> None:
    """Timeline lens (Phase E): tag each version tick with the fingerprint
    dimensions that changed from the previous tick (code/prompt/config/model)."""
    for events in timelines.values():
        prev: dict[str, Any] | None = None
        for e in events:
            if e.get("kind") != "version":
                continue
            cur = e.get("version", {}) or {}
            e["changed"] = ([d for d in VERSION_DIMENSIONS if prev.get(d) != cur.get(d)]
                            if prev is not None else [])
            prev = cur


def blast_radius(view: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Lens 6 — what breaks if you touch `node_id`.

    Returns the transitive downstream dependents (everything that reaches
    node_id by following dependency edges) and the direct contract coupling
    (sum of edge kinds) of each immediate dependent, for ranking. The render
    page computes the same thing client-side; this is the tested reference.
    """
    reverse: dict[str, list[str]] = {}
    for edge in view["edges"]:
        reverse.setdefault(edge["to"], []).append(edge["from"])

    seen: set[str] = set()
    stack = [node_id]
    while stack:
        cur = stack.pop()
        for dep in reverse.get(cur, []):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)

    coupling: dict[str, int] = {}
    for edge in view["edges"]:
        if edge["to"] == node_id:
            coupling[edge["from"]] = coupling.get(edge["from"], 0) + len(edge["kinds"])

    ranked = sorted(coupling, key=lambda n: (-coupling[n], n))
    return {"node": node_id, "dependents": sorted(seen), "directCoupling": coupling, "ranked": ranked}


def render_html(view: dict[str, Any]) -> str:
    """Render the view to a self-contained Universe page with the data embedded.

    This is the static path (`ent render`): the whole `build_view` model is baked
    into the page, so it opens with no server. `ent serve` uses
    `build_universe(None)`, which hydrates live from `/api/graph` instead.
    """
    return build_universe(view)


def build_universe(view: dict[str, Any] | None) -> str:
    """The Universe render surface (SPEC.md §4, LEXICON → Universe).

    `view` embedded → static snapshot; `None` → the page fetches `/api/graph`
    and enables live actions (steer / eval / revert). One template, two modes.
    """
    if view is None:
        embedded = "null"
    else:
        # Embed real JSON in a <script type="application/json"> block. A <script>
        # is a raw-text element (entities are NOT decoded), so escape only what
        # could break out of it — `</script>`, comments, and the JS line
        # separators — via \u escapes that keep the payload valid JSON.
        embedded = (json.dumps(view)
                    .replace("<", "\\u003c").replace(">", "\\u003e")
                    .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    return _UNIVERSE.replace("__DATA__", embedded)


def write_html(root: Path, out: Path | None = None) -> Path:
    """Build + write the render page. Returns the path written."""
    root = Path(root)
    view = build_view(root)
    out = Path(out) if out else root / "entiendo" / "render.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(view))
    return out


def serve(root: Path, port: int = 7373, lens: str = "structure") -> None:  # pragma: no cover
    """Serve the render page on localhost. Read-only; rebuilds on each request."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = render_html(build_view(root)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"entiendo render surface on http://127.0.0.1:{port}  (lens: {lens}, Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


# --------------------------------------------------------------------------- #
# The Universe template — self-contained (inline CSS/JS, no external requests),
# theme-aware, reduced-motion aware. Loaded from a sibling data file so the JS
# (backticks, ${…}, regex) needs no Python escaping. `__DATA__` is replaced with
# the embedded view (static) or the literal `null` (served → fetch /api/graph).
# --------------------------------------------------------------------------- #

_UNIVERSE = (Path(__file__).parent / "universe.html").read_text(encoding="utf-8")


