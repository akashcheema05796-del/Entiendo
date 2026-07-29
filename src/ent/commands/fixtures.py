"""`ent fixtures <unit>` — propose tier0 smoke fixtures from recorded traces.

Reads the traces that exercised a unit and prints (or writes) one skeleton smoke
fixture per trace: named after the request, with the dependency stubs pre-wired
and error traces flagged. The `input` payload is a placeholder — traces don't
record it — so the human fills that and moves the row into the real fixture.

Exit codes:
  0  proposals produced (or none, cleanly)
  2  environment problem (deps missing)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..fixtures import propose_from_traces, write_proposals


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "fixtures",
        help="propose tier0 smoke fixtures for a unit from recorded traces",
        description="Scaffold smoke-fixture skeletons for a unit from its recorded traces.",
    )
    p.add_argument("unit", help="the unit id to propose fixtures for")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument("--write", action="store_true",
                   help="write proposals to entiendo/proposals/fixtures/ instead of stdout")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        proposals = propose_from_traces(root, args.unit)
    except ModuleNotFoundError as exc:
        print(f"ent fixtures: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    if not proposals:
        print(f"no recorded traces exercise '{args.unit}' — nothing to propose.\n"
              f"record one with history.capture_trace(root, trace_id=...), then re-run.")
        return 0

    if args.write:
        path = write_proposals(root, args.unit, proposals)
        print(f"  wrote {len(proposals)} proposed fixture(s) → {path.relative_to(root)}")
        print("  review, fill each `input`, then move rows into the real smoke fixture.")
        return 0

    print(f"# {len(proposals)} proposed smoke fixture(s) for {args.unit} "
          f"(from traces) — fill each `input`, then move into the real fixture:\n")
    for p in proposals:
        print(json.dumps(p.fixture))
        obs = p.observed
        print(f"  # trace {p.source_trace} · status {obs['status']} · "
              f"{obs['durationMs']}ms · cost {obs['costUsd']}")
        for note in p.notes:
            print(f"  # {note}")
        print()
    return 0
