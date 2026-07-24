"""`ent baseline accept <node>` — promote a pending baseline (Phase 7 §7).

An IMPROVED tier1 run writes a *proposal* to <node-id>.pending.json rather than
moving the baseline itself. Auto-promotion would let a slow drift ratchet the
baseline downward one "improvement" at a time, so promotion is always a human
step.

Exit codes: 0 promoted · 2 nothing pending / node not found
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import baselines
from ..manifest import find_node


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "baseline",
        help="[tier1] manage node eval baselines",
        description="Promote a pending baseline to active.",
    )
    sub = p.add_subparsers(dest="baseline_command", metavar="<subcommand>")

    accept = sub.add_parser("accept", help="promote a pending baseline")
    accept.add_argument("node", help="node id")
    accept.add_argument("--root", default=".", help="project root (default: current directory)")
    accept.set_defaults(handler=_accept)

    p.set_defaults(handler=_no_subcommand)


def _no_subcommand(args: argparse.Namespace) -> int:
    print("ent baseline: expected a subcommand (accept)")
    return 2


def _accept(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    node = find_node(root, args.node)
    if node is None:
        print(f"ent baseline: no node with id '{args.node}' under {root}")
        return 2

    pending = baselines.read_pending(root, args.node)
    if pending is None:
        print(f"ent baseline: no pending baseline for {args.node}")
        return 2

    baselines.accept_pending(root, args.node)
    print(f"✓ promoted baseline for {args.node}: {pending.get('metric')}={pending.get('baseline')}")
    return 0
