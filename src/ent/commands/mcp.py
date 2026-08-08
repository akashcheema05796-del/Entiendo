"""`ent mcp` — serve Entiendo as an MCP server over stdio for Claude Code.

Claude Code becomes the editing model: it reads through `get_node_context`
(scoped, claims-only) and writes through `apply_edit` (boundary-enforced,
tier0-verified). Register in a project with `.mcp.json`:

    { "mcpServers": { "entiendo": { "command": "ent", "args": ["mcp", "--root", "."] } } }

Exit codes: 0 ok · 2 manifests invalid (run `ent validate`)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..mcp_server import serve_mcp
from ..validation import validate_root


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "mcp",
        help="[L5] serve Entiendo as an MCP server (stdio) for Claude Code",
        description="Expose the map, scoped context, evals, and boundary-enforced "
                    "edits as MCP tools. Claude Code is the model.",
    )
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument(
        "--allow-invalid", action="store_true",
        help="start even if manifests fail validation (retrofit workflows)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    from ..manifest import discover

    root = Path(args.root).resolve()
    # An UNMANAGED repo (zero manifests) is a legitimate starting state — the
    # retrofit tools exist precisely to work there. Only manifests that exist
    # and fail validation block startup.
    if discover(root):
        report = validate_root(root)
        if not report.ok and not args.allow_invalid:
            print("ent mcp: manifests are invalid — run `ent validate`, "
                  "or pass --allow-invalid for retrofit workflows.")
            return 2
    serve_mcp(root)
    return 0
