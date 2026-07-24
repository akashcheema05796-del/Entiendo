"""`ent render` — L4. Build/serve the render surface (lenses 1, 4, 5).

By default writes a self-contained HTML file (entiendo/render.html). With
--serve it serves the page on localhost, rebuilding on each request. Read-only
observer, never in the request path (Invariant 2).

Exit codes:
  0  ok
  2  environment problem, or manifests invalid (run `ent validate`)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..render import serve, write_html
from ..validation import validate_root


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "render",
        help="[L4] build/serve the render surface (lenses 1, 4, 5)",
        description="Build the generated system map. Read-only observer.",
    )
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument("--out", help="output HTML path (default: entiendo/render.html)")
    p.add_argument("--serve", action="store_true", help="serve on localhost instead of writing a file")
    p.add_argument("--port", type=int, default=7373, help="port for --serve (default: 7373)")
    p.add_argument(
        "--lens",
        choices=["structure", "flow", "trace", "health", "timeline", "blast"],
        default="structure",
        help="initial lens (default: structure)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    try:
        report = validate_root(root)
        if not report.ok:
            print("ent render: manifests are invalid — run `ent validate` first.")
            return 2
        if args.serve:
            serve(root, port=args.port, lens=args.lens)
            return 0
        out = write_html(root, Path(args.out) if args.out else None)
    except ModuleNotFoundError as exc:
        print(f"ent render: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    print(f"  wrote  {out}")
    print(f"\n✓ render surface built — open it, or `ent render --serve`")
    return 0
