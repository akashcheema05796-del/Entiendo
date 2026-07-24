"""`ent render` — L4. Serve the render surface (one topology, six lenses).

STUB. Wired but not implemented — Phase 4/5 (L4) fills this in.

Planned behaviour:
  - serve the web surface reading graph.json + history/ + eval results
  - lenses ship in order: structure, health, timeline (Phase 4),
    then flow, trace, blast radius (Phase 5)
  - read-only observer — never in the request path (Invariant 2)
"""

from __future__ import annotations

import argparse

from ._stub import not_implemented


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "render",
        help="[L4] serve the render surface (six lenses)",
        description="Serve the generated system map. Read-only observer.",
    )
    p.add_argument("--port", type=int, default=7373, help="port to serve on")
    p.add_argument(
        "--lens",
        choices=["structure", "flow", "trace", "health", "timeline", "blast"],
        default="structure",
        help="initial lens (default: structure)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    return not_implemented(
        command="render",
        phase="Phase 4 (L3/L4: History + render)",
        summary="Serve the web surface: structure, health, timeline first; "
        "flow, trace, blast radius follow in Phase 5.",
        acceptance="a node's version change is visible on the timeline within one "
        "commit; health colour matches `ent eval` output.",
    )
