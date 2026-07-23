"""`ent init` — L0. Scaffold entiendo/ and a first node manifest.

STUB. Wired but not implemented — Phase 1 (L0) fills this in.

Planned behaviour:
  - create /entiendo/ (graph.json, coverage.json, baselines/, history/)
  - drop a starter entiendo.node.yaml next to a chosen source module
  - never overwrite generated artifacts that already exist
"""

from __future__ import annotations

import argparse

from ._stub import not_implemented


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "init",
        help="[L0] scaffold entiendo/ + a first node manifest",
        description="Scaffold the entiendo/ layout and a first node manifest.",
    )
    p.add_argument(
        "--path",
        default=".",
        help="project root to initialise (default: current directory)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    return not_implemented(
        command="init",
        phase="Phase 1 (L0: Boundaries)",
        summary="Scaffold entiendo/ (graph.json, coverage.json, baselines/, history/) "
        "and a starter node manifest.",
        acceptance="a repo with 3 hand-written manifests validates; a malformed one "
        "fails with a useful error.",
    )
