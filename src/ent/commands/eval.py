"""`ent eval` — run a node's evals and print a verdict (Phase 7).

  ent eval <node>            tier0 (executes the node, default)
  ent eval <node> --tier 1   golden dataset
  ent eval --all             every node, tier0 — the health sweep
  ent eval --all --tier 1    every node, golden — the pre-merge gate

Exit codes (Phase 7 §11): 0 pass/within-band · 1 RED/REGRESSED · 2 ERROR ·
4 UNSTABLE/DEGRADED. An advisory tier1 run (unblessed dataset) never blocks (0).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import verdicts
from ..evals.runner import run_tier0, run_tier1, run_tier2
from ..manifest import discover, load, Node, find_node


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "eval",
        help="[L2/tier1] run a node's evals — tier0 executes the node",
        description="Run the tiered evals for a node and print a verdict.",
    )
    p.add_argument("node", nargs="?", help="node id, e.g. retrieval.chunk_ranker")
    p.add_argument("--all", action="store_true", help="run every node")
    p.add_argument("--tier", choices=["0", "1", "2"], default="0",
                   help="eval tier: 0 execute (default), 1 golden, 2 LLM judge")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    runners = {"0": run_tier0, "1": run_tier1, "2": run_tier2}
    runner = runners[args.tier]

    try:
        if args.all:
            nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
        else:
            if not args.node:
                print("ent eval: give a node id or --all")
                return 2
            node = find_node(root, args.node)
            if node is None:
                print(f"ent eval: no node with id '{args.node}' under {root}")
                return 2
            nodes = [node]
    except ModuleNotFoundError as exc:
        print(f"ent eval: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    codes: list[int] = []
    for node in sorted(nodes, key=lambda n: n.id):
        result = runner(node, root)
        _print_result(result, tier=args.tier, verbose=not args.all)
        code = 0 if result.advisory else verdicts.exit_code(result.verdict)
        codes.append(code)

    # Overall exit for --all: block (1) > error (2) > unstable (4) > pass (0).
    for c in (1, 2, 4):
        if c in codes:
            return c
    return 0


def _print_result(result, *, tier: str, verbose: bool) -> None:
    mark = {"pass": "✓", "fail": "✗", "skip": "–", "error": "!"}
    if verbose:
        for check in result.checks:
            print(f"  {mark.get(check.status, '?')} {check.type:16} {check.detail}")
        print()
        advisory = "  [ADVISORY]" if result.advisory else ""
        print(f"{_glyph(result.verdict)} {result.node_id}: {result.verdict} "
              f"(tier{tier}, {result.duration_ms:.0f}ms){advisory}")
    else:
        advisory = " [advisory]" if result.advisory else ""
        print(f"  {_glyph(result.verdict)} {result.node_id:26} {result.verdict}{advisory}")


def _glyph(verdict: str) -> str:
    return {
        "GREEN": "●", "WITHIN_BAND": "●", "IMPROVED": "▲",
        "RED": "✗", "REGRESSED": "✗",
        "UNTESTED": "○", "ERROR": "!", "UNSTABLE": "~", "DEGRADED": "$",
    }.get(verdict, "?")
