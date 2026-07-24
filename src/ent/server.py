"""L5 — the interactive edit surface (`ent serve`).

A small backend over the functions that already exist — build_view (map),
assemble_context (scoped context), run_tier0/1 (evals), agent.propose_edit (the
model), editloop.review_edit (boundary + verdict + blast + approval) — plus a
single-page frontend. Click a node, see it, describe a change; the model edits
within the node's claims, tier0 reruns, and the verdict + blast radius surface.

Design guarantees:
  - The map is read-only (Invariant 2). Only the /edit and /revert endpoints
    write, and /edit writes ONLY within the node's claims (agent.propose_edit
    rejects the rest; review_edit re-checks the boundary).
  - No new hard dependency: the HTTP layer is stdlib http.server. The model is an
    optional extra; without it, /edit returns a clear 503 and everything else works.

The route logic is a pure function (`handle_api`) so it is unit-tested without a
live socket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import agent, verdicts
from .editloop import assemble_context, review_edit
from .evals.runner import run_tier0, run_tier1
from .manifest import find_node
from .render import build_view

_BACKUP_DIR = "entiendo/.edit-backups"


def handle_api(root: Path, method: str, path: str, body: dict[str, Any] | None,
               *, client: Any | None = None) -> tuple[int, dict[str, Any]]:
    """Pure request router. Returns (status_code, json_payload)."""
    root = Path(root)
    parts = [p for p in path.strip("/").split("/") if p]  # e.g. ["api","node","x.y","edit"]

    try:
        if parts == ["api", "graph"] and method == "GET":
            return 200, build_view(root)

        if len(parts) >= 3 and parts[:2] == ["api", "node"]:
            node_id = parts[2]
            action = parts[3] if len(parts) > 3 else None

            if find_node(root, node_id) is None:
                return 404, {"error": f"no node '{node_id}'"}

            if action == "context" and method == "GET":
                return 200, assemble_context(root, node_id).as_dict()

            if action == "eval" and method == "POST":
                tier = str((body or {}).get("tier", "0"))
                node = find_node(root, node_id)
                result = (run_tier1 if tier == "1" else run_tier0)(node, root)
                return 200, result.as_dict()

            if action == "edit" and method == "POST":
                return _edit(root, node_id, (body or {}).get("instruction", ""), client)

            if action == "revert" and method == "POST":
                return _revert(root, node_id)

        return 404, {"error": "not found"}
    except Exception as exc:  # never leak a stack to the client
        return 500, {"error": str(exc)}


def _edit(root: Path, node_id: str, instruction: str, client: Any | None) -> tuple[int, dict]:
    if not instruction.strip():
        return 400, {"error": "empty instruction"}

    ctx = assemble_context(root, node_id)
    try:
        proposal = agent.propose_edit(ctx, instruction, client=client)
    except agent.AgentUnavailable as exc:
        return 503, {"error": f"editing model unavailable: {exc}"}

    diffs: dict[str, dict[str, str]] = {}
    for rel, new_content in proposal["files"].items():
        before = ctx.claimed_files.get(rel, "")
        diffs[rel] = {"before": before, "after": new_content}
        _backup(root, node_id, rel, before)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content)

    outcome = review_edit(root, node_id, list(proposal["files"]))
    return 200, {
        "summary": proposal["summary"],
        "changed": sorted(proposal["files"]),
        "rejected": proposal["rejected"],
        "diffs": diffs,
        "outcome": outcome.as_dict(),
    }


def _backup(root: Path, node_id: str, rel: str, content: str) -> None:
    dest = Path(root) / _BACKUP_DIR / node_id / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)


def _revert(root: Path, node_id: str) -> tuple[int, dict]:
    backup_root = Path(root) / _BACKUP_DIR / node_id
    if not backup_root.exists():
        return 404, {"error": "nothing to revert"}
    restored = []
    for backup in backup_root.rglob("*"):
        if backup.is_file():
            rel = backup.relative_to(backup_root)
            (Path(root) / rel).write_text(backup.read_text())
            restored.append(rel.as_posix())
            backup.unlink()
    node = find_node(root, node_id)
    return 200, {"restored": sorted(restored), "verdict": run_tier0(node, root).verdict}


# --------------------------------------------------------------------------- #
# http server
# --------------------------------------------------------------------------- #

def serve(root: Path, port: int = 7373, *, client: Any | None = None) -> None:  # pragma: no cover
    from http.server import BaseHTTPRequestHandler, HTTPServer

    root = Path(root).resolve()
    app_html = build_app_html().encode()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: Any, content_type: str) -> None:
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/" or self.path == "":
                self._send(200, app_html, "text/html; charset=utf-8")
            else:
                status, payload = handle_api(root, "GET", self.path, None, client=client)
                self._send(status, payload, "application/json")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else {}
            status, payload = handle_api(root, "POST", self.path, body, client=client)
            self._send(status, payload, "application/json")

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"entiendo edit surface on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


def build_app_html() -> str:
    return _APP_HTML


_APP_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entiendo — edit surface</title>
<style>
  :root { --bg:#f7f7f8; --panel:#fff; --ink:#1c1c22; --muted:#6b6b78; --line:#e3e3e8;
    --green:#22c55e; --red:#ef4444; --grey:#9aa0aa; --amber:#f59e0b; --accent:#3b82f6; }
  @media (prefers-color-scheme: dark) { :root { --bg:#141417; --panel:#1c1c22; --ink:#ececf1;
    --muted:#9a9aa8; --line:#2c2c34; } }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    background:var(--bg); color:var(--ink); display:grid; grid-template-columns:340px 1fr; height:100vh; }
  header { grid-column:1/3; padding:14px 20px; border-bottom:1px solid var(--line); }
  h1 { margin:0; font-size:16px; } .sub { color:var(--muted); font-size:12px; }
  #list { overflow:auto; border-right:1px solid var(--line); padding:10px; }
  .node { padding:9px 11px; border:1px solid var(--line); border-left:4px solid var(--line);
    border-radius:9px; margin-bottom:8px; cursor:pointer; background:var(--panel); }
  .node:hover { border-color:var(--accent); }
  .node.sel { box-shadow:0 0 0 1px var(--accent) inset; }
  .node .id { font-weight:600; font-size:13px; word-break:break-all; }
  .node .meta { color:var(--muted); font-size:12px; }
  .dot { display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px; }
  #detail { overflow:auto; padding:18px 22px; }
  .empty { color:var(--muted); }
  h2 { font-size:15px; margin:0 0 4px; } code { font-family:ui-monospace,Menlo,monospace; font-size:12px; }
  .pill { display:inline-block;font-size:11px;padding:1px 7px;border-radius:20px;border:1px solid var(--line);margin-right:4px; }
  .files li { font-family:ui-monospace,Menlo,monospace; font-size:12px; }
  textarea { width:100%; min-height:70px; border:1px solid var(--line); border-radius:8px;
    background:var(--panel); color:var(--ink); padding:8px; font:13px/1.4 inherit; resize:vertical; }
  button { border:1px solid var(--line); background:var(--panel); color:var(--ink);
    border-radius:8px; padding:7px 13px; cursor:pointer; font-size:13px; }
  button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  .row { display:flex; gap:8px; align-items:center; margin:10px 0; }
  .verdict { font-weight:600; padding:2px 8px; border-radius:6px; color:#fff; }
  pre.diff { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px;
    overflow:auto; font-family:ui-monospace,Menlo,monospace; font-size:12px; max-height:280px; }
  pre.diff .add { color:var(--green); } pre.diff .del { color:var(--red); }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin:12px 0; }
  .muted { color:var(--muted); }
</style>
</head>
<body>
<header>
  <h1>Entiendo — <span class="muted">edit through the node</span></h1>
  <div class="sub" id="summary">loading…</div>
</header>
<div id="list"></div>
<div id="detail"><p class="empty">Select a node on the left.</p></div>
<script>
const COLOUR = {GREEN:'--green',WITHIN_BAND:'--green',IMPROVED:'--green',RED:'--red',
  REGRESSED:'--red',UNTESTED:'--grey',ERROR:'--amber',UNSTABLE:'--amber',DEGRADED:'--amber'};
const cvar = n => getComputedStyle(document.documentElement).getPropertyValue(n)||'#888';
const esc = s => (s??'').toString().replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let view=null, sel=null;

async function api(method, path, body) {
  const r = await fetch(path, {method, headers:{'Content-Type':'application/json'},
    body: body?JSON.stringify(body):undefined});
  return {status:r.status, data: await r.json()};
}

async function load() {
  const {data} = await api('GET','/api/graph');
  view = data;
  document.getElementById('summary').textContent =
    `${data.nodes.length} nodes · coverage ${Math.round(data.coverage.coverage*100)}% · `
    + `executable ${data.executable}/${data.nodeCount} · ${data.reconciled?'reconciled':'drift'}`;
  const list = document.getElementById('list');
  list.innerHTML = data.nodes.map(n => {
    const col = cvar(COLOUR[n.health]||'--line');
    return `<div class="node" data-id="${esc(n.id)}" style="border-left-color:${col}">
      <div class="id"><span class="dot" style="background:${col}"></span>${esc(n.id)}</div>
      <div class="meta">${esc(n.nodeKind)} · ${esc(n.health)}</div></div>`;
  }).join('');
  list.querySelectorAll('.node').forEach(el =>
    el.addEventListener('click', () => selectNode(el.dataset.id)));
}

async function selectNode(id) {
  sel = id;
  document.querySelectorAll('.node').forEach(n => n.classList.toggle('sel', n.dataset.id===id));
  const {data:ctx} = await api('GET', `/api/node/${id}/context`);
  const node = view.nodes.find(n=>n.id===id);
  const files = Object.keys(ctx.claimedFiles||{}).map(p=>`<li>${esc(p)}</li>`).join('');
  const neigh = Object.keys(ctx.neighbourContracts||{}).map(n=>`<span class="pill">${esc(n)}</span>`).join(' ');
  document.getElementById('detail').innerHTML = `
    <h2>${esc(id)}</h2>
    <div class="muted">${esc(node.nodeKind)} · owner ${esc(node.owner||'—')} · v <code>${esc(node.version?.composite||'—')}</code>
      ${node.approvalRequired?'· <span class="pill">approval required</span>':''}</div>
    <div class="card"><b>claimed files</b><ul class="files">${files||'<li class="muted">none</li>'}</ul>
      <b>neighbour contracts</b><div>${neigh||'<span class="muted">none</span>'}</div>
      <div class="muted" style="margin-top:6px">baselines: ${esc(JSON.stringify(ctx.baselines||{}))}</div></div>
    <div class="row">
      <span>health:</span> <span id="verdict" class="verdict" style="background:${cvar(COLOUR[node.health]||'--grey')}">${esc(node.health)}</span>
      <button onclick="runEval('0')">run tier0</button>
      <button onclick="runEval('1')">run tier1</button>
    </div>
    <div class="card">
      <b>describe a change</b> <span class="muted">— the model edits within this node's claims only</span>
      <textarea id="instr" placeholder="e.g. clamp scores into [0,1] before returning"></textarea>
      <div class="row"><button class="primary" id="go" onclick="doEdit()">propose &amp; apply</button>
        <button onclick="doRevert()">revert</button>
        <span id="status" class="muted"></span></div>
    </div>
    <div id="result"></div>`;
}

async function runEval(tier) {
  const {data} = await api('POST', `/api/node/${sel}/eval`, {tier});
  const v = document.getElementById('verdict');
  v.textContent = data.verdict; v.style.background = cvar(COLOUR[data.verdict]||'--grey');
}

function diffHtml(diffs) {
  return Object.entries(diffs).map(([path,d]) => {
    const before = (d.before||'').split('\\n'), after = (d.after||'').split('\\n');
    const lines = [`--- ${esc(path)}`];
    before.forEach(l => { if(!after.includes(l)) lines.push(`<span class="del">- ${esc(l)}</span>`); });
    after.forEach(l => { if(!before.includes(l)) lines.push(`<span class="add">+ ${esc(l)}</span>`); });
    return `<pre class="diff">${lines.join('\\n')}</pre>`;
  }).join('');
}

async function doEdit() {
  const instr = document.getElementById('instr').value.trim();
  if (!instr) return;
  const btn = document.getElementById('go'), status = document.getElementById('status');
  btn.disabled = true; status.textContent = 'asking the model…';
  const {status:code, data} = await api('POST', `/api/node/${sel}/edit`, {instruction:instr});
  btn.disabled = false; status.textContent = '';
  if (code !== 200) { document.getElementById('result').innerHTML =
    `<div class="card"><b style="color:${cvar('--amber')}">${esc(data.error)}</b></div>`; return; }
  const o = data.outcome, col = cvar(COLOUR[o.verdict]||'--grey');
  const v = document.getElementById('verdict'); v.textContent=o.verdict; v.style.background=col;
  document.getElementById('result').innerHTML = `
    <div class="card">
      <div>${esc(data.summary)}</div>
      <div class="row"><span>tier0:</span> <span class="verdict" style="background:${col}">${esc(o.verdict)}</span>
        <span class="pill">${esc(o.status)}</span></div>
      ${data.rejected.length?`<div style="color:${cvar('--amber')}">rejected (outside claims): ${esc(data.rejected.join(', '))}</div>`:''}
      <div class="muted">blast radius: ${(o.blast.dependents||[]).length} dependent(s) ${esc((o.blast.dependents||[]).join(', '))}</div>
      ${diffHtml(data.diffs)}
    </div>`;
  load();
}

async function doRevert() {
  const {data} = await api('POST', `/api/node/${sel}/revert`, {});
  document.getElementById('status').textContent = data.restored
    ? `reverted ${data.restored.length} file(s)` : (data.error||'');
  if (sel) selectNode(sel); load();
}

load();
</script>
</body>
</html>
"""
