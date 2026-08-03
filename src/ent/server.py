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

from . import agent, steering, verdicts
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

        # --- the Bridge (Phase C): steer here, the workload acts, verdict returns ---
        if parts == ["api", "steer"] and method == "POST":
            unit = (body or {}).get("unit", "")
            instruction = (body or {}).get("instruction", "")
            if not str(instruction).strip():
                return 400, {"error": "empty instruction"}
            if find_node(root, unit) is None:
                return 404, {"error": f"no node '{unit}'"}
            return 200, steering.enqueue(root, unit, instruction)

        if parts == ["api", "steering"] and method == "GET":
            return 200, steering.poll(root)

        # --- approval, for real (H0.3): gated edits land as proposals ---
        if parts == ["api", "proposals"] and method == "GET":
            return 200, {"proposals": steering.proposals(root)}

        if len(parts) == 4 and parts[:2] == ["api", "proposals"] and method == "POST":
            pid, action = parts[2], parts[3]
            if action == "approve":
                result = steering.approve(root, pid)
            elif action == "reject":
                result = steering.reject(root, pid)
            else:
                return 404, {"error": "not found"}
            return (404 if "error" in result else 200), result

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

            if action == "replay" and method == "POST":   # Timeline lens action (H3)
                against = (body or {}).get("against", "")
                from .replay import replay
                return 200, replay(root, node_id, against)

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

    from . import claims as claims_mod
    from .manifest import find_node as _find
    node = _find(root, node_id)

    diffs: dict[str, dict[str, str]] = {}
    for raw_rel, new_content in proposal["files"].items():
        # the single claims authority (v6 1.4): the agent's own filter is a
        # courtesy — the WRITE is gated on realpath + containment + claims.
        rel = claims_mod.claimed_rel(root, node, raw_rel)
        if rel is None:
            proposal["rejected"].append(raw_rel)
            continue
        before = ctx.claimed_files.get(rel, "")
        diffs[rel] = {"before": before, "after": new_content}
        _backup(root, node_id, rel, before)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content)

    outcome = review_edit(root, node_id, list(diffs))
    return 200, {
        "summary": proposal["summary"],
        "changed": sorted(diffs),
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
    """The `ent serve` frontend: the Universe in live mode (hydrates from
    `/api/graph`, enabling steer / eval / revert). `ent render` embeds the data
    instead; both share one template (`render.build_universe`)."""
    from .render import build_universe
    return build_universe(None)
