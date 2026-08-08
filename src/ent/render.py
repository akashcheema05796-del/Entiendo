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
    tier1_latest = _tier1_latest(root)
    blind = result.graph.get("possibleUndeclaredDynamicDep", [])

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
            # who blessed this unit's golden baseline (V3) — the human gate, visible
            "blessing": _blessing(root, gnode["id"]),
            # latest tier1 statistical verdict + CI (v6 2.2) — significance on the map
            "tier1": tier1_latest.get(gnode["id"]),
            # extractor blind spots (v6 3.5) — dynamic constructs the import
            # walk can't see; the dossier shows them as honesty, not alarm
            "blindSpots": [w for w in blind if w["node"] == gnode["id"]],
            # v7 payload — windows render entirely from this; no fetch, no
            # server dependency, and no invented statistics (pValue does not
            # exist here: the engine is CI-bounds, so `significant` means the
            # 95% CI excludes zero).
            "evals": _evals_rollup(result0, tier1_latest.get(gnode["id"])),
            "history": _history_rows(history.timeline(root, gnode["id"])),
            "neighbours": _neighbours(gnode["id"], result.graph["edges"]),
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
        "payloadVersion": 2,
        "commit": gitinfo.short_commit(root),
        "coverage": result.coverage,
        "nodes": sorted(node_views, key=lambda n: n["id"]),
        "edges": result.graph["edges"],
        "dependencyCycles": result.graph.get("dependencyCycles", []),
        "reconciled": result.ok,
        "executable": executable,
        "nodeCount": len(node_views),
        "timelines": timelines,
        "traces": [_trace_view(t) for t in trace_events],
        "traffic": traffic,
        "commits": commits,          # the Timeline scrubber's axis (H3)
        # v7 phase 4 — saved window layout (user state; stale unit ids dropped)
        "workspace": _load_workspace(root, {n["id"] for n in node_views}),
    }


def _load_workspace(root: Path, known_ids: set[str]) -> dict[str, Any] | None:
    """entiendo/workspace.json if present and sane; unknown unit ids are
    dropped silently (a deleted LU must not crash the page)."""
    path = Path(root) / "entiendo" / "workspace.json"
    if not path.exists():
        return None
    try:
        ws = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(ws, dict) or ws.get("version") != 1:
        return None
    ws["windows"] = [w for w in (ws.get("windows") or [])
                     if isinstance(w, dict) and w.get("id") in known_ids]
    return ws


def _evals_rollup(result0: Any, t1: dict[str, Any] | None) -> dict[str, Any]:
    """Per-unit eval summary for the window `evals` tab (v7 payload)."""
    checks = getattr(result0, "checks", None) or []
    graded = [c for c in checks if c.status in ("pass", "fail")]
    tier0 = {"passed": sum(1 for c in graded if c.status == "pass"),
             "total": len(graded), "verdict": getattr(result0, "verdict", None),
             "lastRunIso": gitinfo.now_iso()}
    tier1 = None
    if t1 is not None:
        spread = t1.get("spread")
        mean, base = t1.get("mean"), t1.get("baseline")
        ci_lo, ci_hi = t1.get("ciLow"), t1.get("ciHigh")
        label = t1.get("statVerdict")
        # zero spread = a golden set that cannot discriminate — flag in the
        # PAYLOAD, not in JS (plan hard rule)
        if spread == 0.0:
            label = f"{label} — non-discriminating (zero spread)"
        tier1 = {"score": mean, "baseline": base,
                 "delta": (round(mean - base, 4)
                           if mean is not None and base is not None else None),
                 "runs": t1.get("runs"), "nRows": t1.get("nRows"),
                 "ciLow": ci_lo, "ciHigh": ci_hi,
                 "significant": (ci_lo is not None and ci_hi is not None
                                 and (ci_hi < 0 or ci_lo > 0)),
                 "spread": spread, "verdictLabel": label,
                 "blessed": t1.get("blessed")}
    return {"tier0": tier0, "tier1": tier1, "tier2": None}


def _history_rows(timeline: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """Last `limit` history events as window rows — blessedBy passes through
    VERBATIM (never defaulted, never inferred; null renders as null)."""
    rows = []
    for e in timeline[-limit:]:
        rows.append({
            "version": (e.get("composite") or "")[:12] or None,
            "iso": e.get("ts"),
            "summary": e.get("kind"),
            "evalSummary": e.get("verdict"),
            "blessedBy": e.get("blessedBy"),
        })
    return rows


def _neighbours(node_id: str, edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Both directions, with the reconciler's `verified` verbatim — if nothing
    verified an edge, `false` IS the correct output."""
    out = [{"id": e["to"], "rel": "/".join(e.get("kinds") or []),
            "verified": bool(e.get("verified"))}
           for e in edges if e["from"] == node_id]
    inc = [{"id": e["from"], "rel": "/".join(e.get("kinds") or []),
            "verified": bool(e.get("verified"))}
           for e in edges if e["to"] == node_id]
    return {"out": out, "in": inc}


def _tier1_latest(root: Path) -> dict[str, dict[str, Any]]:
    """Latest tier1 stat verdict per unit from evals.jsonl (v6 2.2).

    The health lens blends this with tier0: red only on statistically meaningful
    movement — WITHIN_BAND is a first-class calm state, UNSTABLE means
    underpowered, not broken.
    """
    import json as _json

    path = Path(root) / "entiendo" / "history" / "evals.jsonl"
    if not path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = _json.loads(line)
        except ValueError:
            continue
        if row.get("tier") != 1 or not row.get("nodeId"):
            continue
        latest[row["nodeId"]] = {
            "statVerdict": row.get("verdict"),
            "ciLow": row.get("ciLow"), "ciHigh": row.get("ciHigh"),
            "nRows": row.get("nRows"), "mean": row.get("mean"),
            "baseline": row.get("baseline"),
            "verdictMethod": row.get("verdictMethod"),
            "blessed": row.get("blessed"), "ts": row.get("ts"),
            "spread": row.get("spread"), "runs": row.get("n"),
        }
    return latest


def _blessing(root: Path, node_id: str) -> dict[str, Any] | None:
    """The current baseline's blesser + date (V3), or None if unblessed."""
    from . import baselines
    rec = baselines.read_bless(root, node_id)
    if not rec:
        return None
    return {"blessedBy": rec.get("blessedBy"), "blessedAt": rec.get("blessedAt")}


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
            # label honesty (v6 5.4): below ~20 samples the 95th percentile IS
            # the max — say so instead of dressing a max up as a percentile.
            "p95Basis": (("p95" if len(lat) >= 20 else f"max of {len(lat)}")
                         if lat else None),
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


