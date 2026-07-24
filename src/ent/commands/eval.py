"""`ent eval <node>` — L2. Run a node's evals and print a verdict.

tier0 is implemented here (deterministic, sub-second). tier1 (golden datasets)
and tier2 (LLM judge) are separate, more expensive tiers — they announce
themselves rather than pretending to run.

Exit codes:
  0  green (all tier0 checks pass)
  1  red (a tier0 check failed)
  2  node not found / environment problem
  3  requested tier not implemented in this phase
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..evals.runner import run_tier0
from ..manifest import find_node


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "eval",
        help="[L2] run a node's evals (tier0 by default)",
        description="Run the tiered evals for a node and print a verdict.",
    )
    p.add_argument("node", help="node id, e.g. retrieval.chunk_ranker")
    p.add_argument(
        "--tier",
        choices=["0", "1", "2"],
        default="0",
        help="eval tier to run (default: 0 — deterministic, sub-second)",
    )
    p.add_argument(
        "--root",
        default=".",
        help="project root to run in (default: current directory)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    if args.tier != "0":
        tier_name = {"1": "golden datasets", "2": "LLM judge"}[args.tier]
        print(
            f"ent eval --tier {args.tier}: not implemented yet ({tier_name}). "
            "tier0 is available now; tier1/tier2 land in a later phase."
        )
        return 3

    try:
        node = find_node(root, args.node)
    except ModuleNotFoundError as exc:
        print(f"ent eval: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    if node is None:
        print(f"ent eval: no node with id '{args.node}' under {root}")
        return 2

    try:
        result = run_tier0(node, root)
    except ModuleNotFoundError as exc:
        print(f"ent eval: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    mark = {"pass": "✓", "fail": "✗", "skip": "–"}
    for check in result.checks:
        print(f"  {mark.get(check.status, '?')} {check.type:18} {check.detail}")

    print()
    verdict = result.verdict.upper()
    print(f"{'●' if result.verdict == 'green' else '✗'} {args.node}: {verdict} "
          f"(tier0, {result.duration_ms:.0f}ms)")
    return 0 if result.verdict == "green" else 1
