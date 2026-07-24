"""`ent edit <node>` — L5. The scoped edit loop (SPEC.md §6).

Without --changed: assemble and show the scoped context for a node — the files
and neighbour contracts that would enter the AI's window, and nothing else. This
is the retrieval index in action (the AI edits through the node, not the repo).

With --changed <paths...>: review a proposed edit — boundary check (confined to
claims?), tier0 rerun (pass/fail), blast radius (what's downstream at risk), and
the approval gate.

Exit codes:
  0  context shown, or edit ready-to-merge / awaiting-signoff
  1  edit blocked (boundary violation or tier0 red)
  2  node not found / environment problem
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..editloop import assemble_context, review_edit


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "edit",
        help="[L5] scoped edit loop: context + boundary + verdict + approval",
        description="Assemble a node's scoped edit context, or review a proposed edit.",
    )
    p.add_argument("node", help="node id, e.g. retrieval.chunk_ranker")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument(
        "--changed",
        nargs="*",
        metavar="PATH",
        help="paths edited in this change — review them against the node boundary",
    )
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    try:
        if args.changed is not None:
            return _review(root, args)
        return _context(root, args)
    except KeyError as exc:
        print(f"ent edit: {exc}")
        return 2
    except ModuleNotFoundError as exc:
        print(f"ent edit: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2


def _context(root: Path, args: argparse.Namespace) -> int:
    ctx = assemble_context(root, args.node)
    if args.json:
        print(json.dumps(ctx.as_dict(), indent=2))
        return 0

    print(f"scoped context for {args.node}\n")
    print(f"  claimed files ({len(ctx.claimed_files)}) — the only bodies loaded:")
    for path in ctx.claimed_files:
        print(f"    • {path}")
    print(f"\n  neighbour contracts ({len(ctx.neighbour_contracts)}) — contracts only, no bodies:")
    for nid in ctx.neighbour_contracts:
        print(f"    ◦ {nid}")
    print(f"\n  recent evals: {len(ctx.recent_evals)}   baselines: {ctx.baselines or '—'}")
    print("\n  everything else in the repo is excluded by construction.")
    return 0


def _review(root: Path, args: argparse.Namespace) -> int:
    outcome = review_edit(root, args.node, args.changed or [])
    if args.json:
        print(json.dumps(outcome.as_dict(), indent=2))
        return 0 if not outcome.status.startswith("blocked") else 1

    b = outcome.boundary
    print(f"edit review for {args.node}\n")
    print(f"  boundary: {'✓ within claims' if b.within_claims else '✗ VIOLATION'}")
    for f in b.inside:
        print(f"    ✓ {f}")
    for f in b.violations:
        print(f"    ✗ {f}  (not claimed — needs a boundary-change proposal)")

    mark = {"pass": "✓", "fail": "✗", "skip": "–"}
    print(f"\n  tier0: {outcome.verdict.upper()}")
    for c in outcome.checks:
        print(f"    {mark.get(c['status'], '?')} {c['type']}")

    dependents = outcome.blast.get("dependents", [])
    print(f"\n  blast radius: {len(dependents)} downstream dependent(s)"
          + (f" — {', '.join(dependents)}" if dependents else ""))

    print(f"\n  approval required: {outcome.approval_required}")
    print(f"\n{'●' if not outcome.status.startswith('blocked') else '✗'} {outcome.status}")
    return 0 if not outcome.status.startswith("blocked") else 1
