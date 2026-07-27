"""`ent` — the Entiendo command-line interface.

This is the scaffold wiring for the CLI. Every subcommand is present and
argument-parsed, but the ones past L0 are deliberate stubs that name the phase
which will implement them (see SPEC.md §8, Build order). Build L0 → L5 in strict
order — do not fill in a later command before the earlier phase's acceptance
criteria pass.

    ent init         L0  scaffold entiendo/ + a first node manifest
    ent validate     L0  validate manifests against the schema
    ent extract      L1  emit graph.json + coverage.json; fail on drift
    ent eval <node>  L2  run a node's evals (tier0 by default)
    ent snapshot     L3  record node versions + eval verdicts to history
    ent render       L4  build/serve the render surface (six lenses)
    ent edit <node>  L5  scoped edit loop: context + boundary + verdict + approval
    ent version      -   print version + apiVersion
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __api_version__, __version__
from .commands import init as init_cmd
from .commands import validate as validate_cmd
from .commands import extract as extract_cmd
from .commands import eval as eval_cmd
from .commands import snapshot as snapshot_cmd
from .commands import render as render_cmd
from .commands import edit as edit_cmd
from .commands import bless as bless_cmd
from .commands import baseline as baseline_cmd
from .commands import retrofit as retrofit_cmd
from .commands import serve as serve_cmd
from .commands import mcp as mcp_cmd
from .commands import pin as pin_cmd
from .commands import replay as replay_cmd
from .commands import new as new_cmd


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ent",
        description="Entiendo — the node is the unit of work.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ent {__version__} ({__api_version__})",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    init_cmd.register(sub)
    validate_cmd.register(sub)
    extract_cmd.register(sub)
    eval_cmd.register(sub)
    snapshot_cmd.register(sub)
    render_cmd.register(sub)
    edit_cmd.register(sub)
    bless_cmd.register(sub)
    baseline_cmd.register(sub)
    retrofit_cmd.register(sub)
    serve_cmd.register(sub)
    mcp_cmd.register(sub)
    pin_cmd.register(sub)
    replay_cmd.register(sub)
    new_cmd.register(sub)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    handler = getattr(args, "handler", None)
    if handler is None:  # pragma: no cover - defensive
        parser.print_help()
        return 2

    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
