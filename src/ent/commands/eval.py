"""`ent eval` — run a unit's evals and print a verdict (Phase 7).

  ent eval <unit>                 reflex (executes the unit, default)
  ent eval <unit> --tier golden   golden dataset
  ent eval --all                  every unit, reflex — the health sweep
  ent eval --all --tier golden    every unit, golden — the pre-merge gate

Tiers speak the lexicon: reflex (=0), golden (=1), judge (=2); the numeric
forms keep working. Exit codes (Phase 7 §11): 0 pass/within-band · 1
RED/REGRESSED · 2 ERROR · 4 UNSTABLE/DEGRADED. An advisory golden run (unblessed
dataset) never blocks (0).
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
        help="[L2] run a unit's evals — reflex executes the unit",
        description="Run the tiered evals (reflex / golden / judge) for a unit and print a verdict.",
    )
    p.add_argument("unit", nargs="?", metavar="unit", help="unit id, e.g. retrieval.chunk_ranker")
    p.add_argument("--all", action="store_true", help="run every unit")
    p.add_argument("--tier", choices=["0", "1", "2", "reflex", "golden", "judge"], default="reflex",
                   help="eval tier: reflex (default, executes), golden (dataset), judge (LLM). "
                        "Numeric 0/1/2 also accepted.")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


# tier lexicon → runner; numeric forms kept for back-compat.
_TIERS = {
    "0": (0, run_tier0), "reflex": (0, run_tier0),
    "1": (1, run_tier1), "golden": (1, run_tier1),
    "2": (2, run_tier2), "judge": (2, run_tier2),
}


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    tier_num, runner = _TIERS[args.tier]

    try:
        if args.all:
            nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
        else:
            if not args.unit:
                print("ent eval: give a unit id or --all")
                return 2
            node = find_node(root, args.unit)
            if node is None:
                print(f"ent eval: no unit with id '{args.unit}' under {root}")
                return 2
            nodes = [node]
    except ModuleNotFoundError as exc:
        print(f"ent eval: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    tier_name = {0: "reflex", 1: "golden", 2: "judge"}[tier_num]
    codes: list[int] = []
    for node in sorted(nodes, key=lambda n: n.id):
        result = runner(node, root)
        _print_result(result, tier=tier_name, verbose=not args.all)
        if tier_num == 1:
            _print_blesser(root, node.id)
        code = 0 if result.advisory else verdicts.exit_code(result.verdict)
        codes.append(code)

    # Overall exit for --all: block (1) > error (2) > unstable (4) > pass (0).
    for c in (1, 2, 4):
        if c in codes:
            return c
    return 0


def _print_blesser(root: Path, node_id: str) -> None:
    """Show who blessed the current baseline, so the human gate is visible (V3)."""
    from .. import baselines
    rec = baselines.read_bless(root, node_id)
    if rec and rec.get("blessedBy"):
        print(f"    baseline blessed by {rec['blessedBy']} on {rec.get('blessedAt', '?')}")


def _print_result(result, *, tier: str, verbose: bool) -> None:
    mark = {"pass": "✓", "fail": "✗", "skip": "–", "error": "!"}
    if verbose:
        for check in result.checks:
            print(f"  {mark.get(check.status, '?')} {check.type:16} {check.detail}")
        print()
        advisory = "  [ADVISORY]" if result.advisory else ""
        print(f"{_glyph(result.verdict)} {result.node_id}: {result.verdict} "
              f"({tier}, {result.duration_ms:.0f}ms){advisory}")
    else:
        advisory = " [advisory]" if result.advisory else ""
        print(f"  {_glyph(result.verdict)} {result.node_id:26} {result.verdict}{advisory}")


def _glyph(verdict: str) -> str:
    return {
        "GREEN": "●", "WITHIN_BAND": "●", "IMPROVED": "▲",
        "RED": "✗", "REGRESSED": "✗",
        "UNTESTED": "○", "ERROR": "!", "UNSTABLE": "~", "DEGRADED": "$",
    }.get(verdict, "?")
