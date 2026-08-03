"""`ent serve` — L5. Interactive edit surface (frontend + backend).

Serves the six-lens map plus the scoped edit loop: click a node, describe a
change, and the model edits within the node's claims, reruns tier0, and shows the
verdict + blast radius. Read-only for the map; only edits write (within claims).

The editing model (Claude Opus 5, via the `anthropic` SDK) is optional: without
it, the explorer and manual evals work and the edit box returns a clear message.

Exit codes: 0 ok · 2 manifests invalid (run `ent validate`)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..server import serve
from ..validation import validate_root


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "serve",
        help="[L5] interactive edit surface — map + AI-assisted edit loop",
        description="Serve the interactive map and scoped edit loop on localhost.",
    )
    _common_args(p)
    p.add_argument(
        "--watch", action="store_true",
        help="live reload: watch manifests/claimed files/history and reload the page",
    )
    p.set_defaults(handler=_run, watch_default=False)

    # v6 4.2 — `ent dev`: serve with live reload on. Same surface, watch=True.
    d = subparsers.add_parser(
        "dev",
        help="[L5] `ent serve --watch` — the map follows your edits live",
        description="Serve the interactive map with live reload (alias for serve --watch).",
    )
    _common_args(d)
    d.set_defaults(handler=_run, watch=True, watch_default=True)


def _common_args(p: "argparse.ArgumentParser") -> None:
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument("--port", type=int, default=7373, help="port to serve on (default: 7373)")
    p.add_argument(
        "--operator", action="store_true",
        help="print the command to run Claude Code as the steering workload, then serve",
    )


def _operator_banner(root: Path) -> str:
    return (
        "\n  ── Operate the Universe with Claude Code ──────────────────────────\n"
        "  1. In THIS repo, start Claude Code:   claude\n"
        "  2. Tell it:                           operate the map\n"
        "     (triggers the `entiendo-operator` skill; it needs the `entiendo`\n"
        "      MCP server from .mcp.json — `ent mcp`)\n"
        "  3. In the browser, click a unit and Steer. Claude Code picks it up,\n"
        "     edits within claims, reflex reruns, and the dossier shows the verdict.\n"
        "  ───────────────────────────────────────────────────────────────────\n"
    )


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = validate_root(root)
    if not report.ok:
        print("ent serve: manifests are invalid — run `ent validate` first.")
        return 2
    if args.operator:
        print(_operator_banner(root))
    serve(root, port=args.port, watch=bool(getattr(args, "watch", False)))
    return 0
