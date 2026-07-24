"""L4 — Render surface. One topology, six lenses (SPEC.md §4). Phase 4 ships
lenses 1 (structure), 4 (health), 5 (timeline).

Read-only observer, never in the request path (Invariant 2): the view is built by
reading manifests + graph + history and by running the same deterministic tier0
evals `ent eval` runs — so the **health colour always matches `ent eval` output**
by construction. Output is a single self-contained HTML file (inline CSS/JS, no
external requests), so it is trivially serveable and inspectable.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from . import gitinfo, history
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
    for gnode in result.graph["nodes"]:
        node = by_id.get(gnode["id"])
        health = run_tier0(node, root).verdict if node else "unknown"
        version = compute_version(node, root) if node else {}
        node_views.append({**gnode, "health": health, "version": version})

    timelines = {n.id: history.timeline(root, n.id) for n in nodes}

    return {
        "apiVersion": "entiendo/v1",
        "commit": gitinfo.short_commit(root),
        "coverage": result.coverage,
        "nodes": sorted(node_views, key=lambda n: n["id"]),
        "edges": result.graph["edges"],
        "reconciled": result.ok,
        "timelines": timelines,
    }


def render_html(view: dict[str, Any]) -> str:
    """Render the view to a self-contained HTML page (lenses 1, 4, 5)."""
    data = html.escape(json.dumps(view), quote=True)
    return _TEMPLATE.replace("__DATA__", data)


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
# template — self-contained, theme-aware, no external requests
# --------------------------------------------------------------------------- #

_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entiendo — system map</title>
<style>
  :root {
    --bg:#f7f7f8; --panel:#fff; --ink:#1c1c22; --muted:#6b6b78; --line:#e3e3e8;
    --compute:#3b82f6; --state:#8b5cf6; --schema:#a855f7; --config:#64748b;
    --external:#f59e0b; --pipeline:#0ea5e9;
    --green:#22c55e; --red:#ef4444; --degraded:#f59e0b;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#141417; --panel:#1c1c22; --ink:#ececf1; --muted:#9a9aa8; --line:#2c2c34; }
  }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:var(--bg); color:var(--ink); }
  header { padding:20px 24px; border-bottom:1px solid var(--line); }
  h1 { margin:0 0 4px; font-size:18px; letter-spacing:.02em; }
  .sub { color:var(--muted); font-size:13px; }
  .tabs { display:flex; gap:6px; padding:12px 24px 0; }
  .tab { padding:8px 14px; border:1px solid var(--line); border-bottom:none;
         border-radius:8px 8px 0 0; cursor:pointer; background:transparent; color:var(--muted); }
  .tab.active { background:var(--panel); color:var(--ink); font-weight:600; }
  main { padding:20px 24px; }
  .group { margin-bottom:22px; }
  .group h2 { font-size:12px; text-transform:uppercase; letter-spacing:.08em;
              color:var(--muted); margin:0 0 10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; }
  .node { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--line);
          border-radius:10px; padding:12px 14px; }
  .node .id { font-weight:600; font-size:13px; word-break:break-all; }
  .node .meta { color:var(--muted); font-size:12px; margin-top:4px; }
  .node .edges { margin-top:8px; font-size:12px; color:var(--muted); }
  .node .edges b { color:var(--ink); font-weight:500; }
  .pill { display:inline-block; font-size:11px; padding:1px 7px; border-radius:20px;
          border:1px solid var(--line); margin-right:4px; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
  table.tl { width:100%; border-collapse:collapse; background:var(--panel);
             border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  table.tl th, table.tl td { text-align:left; padding:8px 12px; border-bottom:1px solid var(--line);
             font-size:12px; }
  table.tl th { color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:.06em; }
  code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
  .cov { font-variant-numeric:tabular-nums; }
</style>
</head>
<body>
<header>
  <h1>Entiendo — <span id="lensName">Structure</span></h1>
  <div class="sub" id="summary"></div>
</header>
<div class="tabs">
  <button class="tab active" data-lens="structure">1 · Structure</button>
  <button class="tab" data-lens="health">4 · Health</button>
  <button class="tab" data-lens="timeline">5 · Timeline</button>
</div>
<main id="main"></main>
<script id="view" type="application/json">__DATA__</script>
<script>
  const view = JSON.parse(document.getElementById('view').textContent);
  const KIND = {compute:'--compute',state:'--state',schema:'--schema',config:'--config',
                external:'--external',pipeline:'--pipeline'};
  const HEALTH = {green:'--green',red:'--red',degraded:'--degraded'};
  const cvar = n => getComputedStyle(document.documentElement).getPropertyValue(n) || '#888';
  const main = document.getElementById('main');
  const esc = s => (s??'').toString().replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

  function summary() {
    const c = view.coverage;
    document.getElementById('summary').innerHTML =
      `${view.nodes.length} nodes · ${view.edges.length} edges · ` +
      `<span class="cov">coverage ${Math.round(c.coverage*100)}%</span> · ` +
      `${view.reconciled ? 'reconciled ✓' : 'drift ✗'}` +
      (view.commit ? ` · @${esc(view.commit)}` : '');
  }

  function byGroup() {
    const groups = {};
    for (const n of view.nodes) (groups[n.group||'(ungrouped)'] ??= []).push(n);
    return groups;
  }

  function edgeLine(n) {
    const outs = view.edges.filter(e => e.from === n.id);
    if (!outs.length) return '';
    return outs.map(e => `<b>${e.kinds.join('/')}</b> ${esc(e.to)}${e.verified?' ✓':''}`).join(' · ');
  }

  function nodeCard(n, colorVar) {
    const col = cvar(colorVar);
    const edges = edgeLine(n);
    return `<div class="node" style="border-left-color:${col}">
      <div class="id">${esc(n.id)}</div>
      <div class="meta">
        <span class="pill">${esc(n.nodeKind)}</span>
        <span class="pill">${esc(n.owner||'')}</span>
        ${n.approvalRequired?'<span class="pill">approval</span>':''}
        v:<code>${esc(n.version?.composite||'—')}</code>
      </div>
      ${edges?`<div class="edges">${edges}</div>`:''}
    </div>`;
  }

  function renderStructure() {
    const g = byGroup();
    main.innerHTML = Object.keys(g).sort().map(name =>
      `<div class="group"><h2>${esc(name)}</h2><div class="grid">` +
      g[name].map(n => nodeCard(n, KIND[n.nodeKind]||'--line')).join('') +
      `</div></div>`).join('');
  }

  function renderHealth() {
    const g = byGroup();
    main.innerHTML = Object.keys(g).sort().map(name =>
      `<div class="group"><h2>${esc(name)}</h2><div class="grid">` +
      g[name].map(n => {
        const hv = HEALTH[n.health]||'--line';
        const card = nodeCard(n, hv);
        const dot = `<span class="dot" style="background:${cvar(hv)}"></span>`;
        return card.replace('<div class="id">', `<div class="id">${dot}`);
      }).join('') + `</div></div>`).join('');
  }

  function renderTimeline() {
    const rows = [];
    for (const n of view.nodes)
      for (const e of (view.timelines[n.id]||[]))
        rows.push(e);
    rows.sort((a,b) => (a.seq??0)-(b.seq??0));
    if (!rows.length) {
      main.innerHTML = `<p class="sub">No history yet. Run <code>ent snapshot</code> to record versions and evals.</p>`;
      return;
    }
    main.innerHTML = `<table class="tl"><thead><tr>
      <th>#</th><th>event</th><th>node</th><th>detail</th><th>commit</th><th>when</th></tr></thead><tbody>` +
      rows.map(e => `<tr>
        <td>${e.seq}</td>
        <td>${e.kind==='version'?'▲ version':'● eval'}</td>
        <td><code>${esc(e.nodeId)}</code></td>
        <td>${e.kind==='version'?`<code>${esc(e.composite)}</code>`:esc(e.verdict)}</td>
        <td><code>${esc(e.commit||'—')}</code></td>
        <td class="sub">${esc(e.ts||'')}</td>
      </tr>`).join('') + `</tbody></table>`;
  }

  const LENSES = {structure:renderStructure, health:renderHealth, timeline:renderTimeline};
  const NAMES = {structure:'Structure', health:'Health', timeline:'Timeline'};
  function select(lens) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.lens===lens));
    document.getElementById('lensName').textContent = NAMES[lens];
    LENSES[lens]();
  }
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => select(t.dataset.lens)));
  summary();
  select('structure');
</script>
</body>
</html>
"""
