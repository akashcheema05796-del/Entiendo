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
from .version import compute_version


def build_view(root: Path) -> dict[str, Any]:
    """Assemble the render model: nodes + edges + health + versions + timelines."""
    root = Path(root)
    nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    result = extract(root)

    by_id = {n.id: n for n in nodes}
    node_views = []
    executable = 0
    for gnode in result.graph["nodes"]:
        node = by_id.get(gnode["id"])
        health = run_tier0(node, root).verdict if node else verdicts.ERROR
        if health != verdicts.UNTESTED:
            executable += 1
        version = compute_version(node, root) if node else {}
        raw = node.raw if node else {}
        contract = raw.get("contract", {}) or {}
        node_views.append({
            **gnode, "health": health,
            "healthColour": verdicts.colour(health), "version": version,
            # dossier fields (logic-first): task + contract, artifacts already in `claims`
            "task": raw.get("task") or raw.get("name") or gnode["id"],
            "invariants": list(contract.get("invariants", []) or []),
        })

    timelines = {n.id: history.timeline(root, n.id) for n in nodes}

    # Trace data (lens 3) + per-node traffic (lens 2 volume).
    trace_events = history.traces(root)
    traffic: dict[str, int] = {}
    for trace in trace_events:
        for hop in trace.get("hops", []):
            traffic[hop["node"]] = traffic.get(hop["node"], 0) + 1

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
        "traces": trace_events,
        "traffic": traffic,
    }


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


