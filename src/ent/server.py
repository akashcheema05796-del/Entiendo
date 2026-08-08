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

        # v7 phase 4 — workspace persistence: user state (window layout, lens,
        # pan), never graph state. Boring on-disk JSON, git-ignorable.
        if parts == ["api", "workspace"] and method == "POST":
            ws = body or {}
            if ws.get("version") != 1:
                return 400, {"error": "workspace version must be 1"}
            wpath = root / "entiendo" / "workspace.json"
            wpath.parent.mkdir(parents=True, exist_ok=True)
            wpath.write_text(json.dumps(ws, indent=2, sort_keys=True) + "\n")
            return 200, {"saved": True}

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
# live reload (v6 4.2) — the map follows the tree, not the other way round
# --------------------------------------------------------------------------- #

WATCH_POLL_S = 0.5           # poll cadence; doubles as the debounce window


def watched_paths(root: Path) -> list[Path]:
    """What `ent dev` watches: manifests, claimed files, history artifacts.

    Best-effort — a manifest that stops parsing mid-edit must not kill the
    watcher (its mtime change still triggers the reload that surfaces the error).
    """
    from .manifest import Node, discover, load

    root = Path(root)
    paths: list[Path] = []
    try:
        for mp in discover(root):
            paths.append(mp)
            try:
                node = Node.from_manifest(load(mp), mp)
            except Exception:
                continue
            paths.extend(root / c for c in node.claims)
    except Exception:                                   # pragma: no cover - defensive
        pass
    hist = root / "entiendo" / "history"
    if hist.exists():
        paths.extend(sorted(hist.glob("*.jsonl")))
    return paths


def snapshot_mtimes(paths: list[Path]) -> dict[str, int | None]:
    """mtime_ns per path (None = missing) — the watcher's change detector."""
    snap: dict[str, int | None] = {}
    for p in paths:
        try:
            snap[str(p)] = p.stat().st_mtime_ns
        except OSError:
            snap[str(p)] = None
    return snap


def resilient_graph(status: int, payload: dict[str, Any],
                    last_good: dict[str, Any] | None,
                    ) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    """Extract failure mid-edit → serve the LAST GOOD view + a drift flag.

    Returns (status, payload, new_last_good). A half-typed manifest must not
    blank the canvas; the page shows a banner until the tree parses again.
    """
    if status == 200:
        return 200, payload, payload
    if last_good is not None:
        return 200, {**last_good,
                     "drift": str(payload.get("error", "extract failed"))}, last_good
    return status, payload, last_good


class _Watcher:  # pragma: no cover — thread glue; the pieces above are unit-tested
    """Background mtime poller. `version` bumps on any watched change."""

    def __init__(self, root: Path) -> None:
        import threading
        self.root = Path(root)
        self.version = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import time as _time
        last = snapshot_mtimes(watched_paths(self.root))
        while not self._stop.is_set():
            _time.sleep(WATCH_POLL_S)
            cur = snapshot_mtimes(watched_paths(self.root))
            if cur != last:
                last = cur
                self.version += 1


# --------------------------------------------------------------------------- #
# http server
# --------------------------------------------------------------------------- #

def check_csrf(header_value: str | None, token: str) -> bool:
    """Handler-level CSRF check (v6 3.4) — pure so it is unit-tested without a
    socket. POSTs must echo the per-process token minted at page render; a
    cross-origin page can *send* a POST to 127.0.0.1 but cannot read the token
    out of our HTML, so it can never pass this check."""
    import hmac
    return bool(header_value) and hmac.compare_digest(str(header_value), token)


def inject_csrf(html: str, token: str) -> str:
    """Embed the CSRF token in the page: a <meta> for inspection and
    window.__entCsrf for the api() helper. Pure string transform (testable)."""
    tag = (f'<meta name="ent-csrf" content="{token}">'
           f"<script>window.__entCsrf={json.dumps(token)}</script>")
    return html.replace("<head>", "<head>\n" + tag, 1)


def version_payload(watcher: Any | None) -> dict[str, Any]:
    """Body for `/api/version`. Separated from the handler so the no-watcher
    contract is unit-testable without a socket (same pattern as check_csrf).

    `watching: False` is the signal that live reload is not running — the page
    stops polling rather than treating the answer as a version that never
    changes.
    """
    if watcher is None:
        return {"version": None, "watching": False}
    return {"version": watcher.version, "watching": True}


def serve(root: Path, port: int = 7373, *, client: Any | None = None,
          watch: bool = False) -> None:  # pragma: no cover
    import secrets
    import time as _time
    # Threading matters (v6 4.2): the /api/version long-poll parks a connection
    # for up to 25s — on a single-threaded server that would starve every other
    # request. Still loopback-only.
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    root = Path(root).resolve()
    csrf_token = secrets.token_hex(16)               # per-process, minted at start
    app_html = inject_csrf(build_app_html(), csrf_token).encode()

    watcher = _Watcher(root) if watch else None
    if watcher:
        watcher.start()
    last_good: list[dict[str, Any] | None] = [None]  # box so Handler can rebind

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
                return
            # live reload (v6 4.2): bounded long-poll — returns when the tree
            # changes or after ~25s, whichever first. The route answers even
            # with no watcher (plain `ent serve`): the page asks on every load,
            # and a 404 there reads as a broken surface. `watching: false` tells
            # it to stop asking instead.
            if urlparse(self.path).path == "/api/version":
                if watcher is not None:
                    qs = parse_qs(urlparse(self.path).query)
                    since = qs.get("since", [""])[0]
                    deadline = _time.time() + 25.0
                    while (str(watcher.version) == since and _time.time() < deadline):
                        _time.sleep(0.25)
                self._send(200, version_payload(watcher), "application/json")
                return
            status, payload = handle_api(root, "GET", self.path, None, client=client)
            if urlparse(self.path).path == "/api/graph":
                # a broken tree serves the last good view + a drift banner
                status, payload, last_good[0] = resilient_graph(status, payload,
                                                                last_good[0])
            self._send(status, payload, "application/json")

        def do_POST(self) -> None:
            # CSRF gate (v6 3.4) — enforced HERE so handle_api stays pure.
            if not check_csrf(self.headers.get("X-Ent-Csrf"), csrf_token):
                self._send(403, {"error": "missing or invalid X-Ent-Csrf token"},
                           "application/json")
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else {}
            status, payload = handle_api(root, "POST", self.path, body, client=client)
            self._send(status, payload, "application/json")

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
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
