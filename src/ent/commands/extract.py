"""`ent extract` — L1. Emit graph.json + coverage.json; fail on drift.

Runs the reconciler over the project and writes the two generated artifacts.
Validates manifests first (L0) — a graph built from invalid manifests is
meaningless. Exits non-zero on drift, double-claims, or dangling dependencies,
naming both nodes (Invariant 5).

Exit codes:
  0  clean — artifacts written, no drift
  1  drift / structural error (also written in default mode so you can inspect)
  2  environment problem, or manifests invalid (run `ent validate`)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..extractor import extract, write_artifacts
from ..validation import validate_root


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "extract",
        help="[L1] emit graph.json + coverage.json; fail on drift",
        description="Reconcile manifests against reality and emit the graph.",
    )
    p.add_argument(
        "--root",
        default=".",
        help="project root to extract (default: current directory)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="fail on drift without writing artifacts (CI mode)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    try:
        report = validate_root(root)
        if not report.ok:
            print("ent extract: manifests are invalid — run `ent validate` first.")
            return 2
        result = extract(root)
    except ModuleNotFoundError as exc:
        print(f"ent extract: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    cov = result.coverage
    graph = result.graph

    if not args.check:
        graph_path, coverage_path = write_artifacts(result, root)
        print(f"  wrote  {graph_path.relative_to(root)}")
        print(f"  wrote  {coverage_path.relative_to(root)}")
        print()

    print(
        f"  {len(graph['nodes'])} node(s), {len(graph['edges'])} edge(s) "
        f"({sum(1 for e in graph['edges'] if e['verified'])} verified)"
    )
    print(
        f"  coverage {cov['coverage'] * 100:.0f}%  "
        f"({cov['claimedCount']} claimed, {cov['acknowledgedUnclaimedCount']} "
        f"acknowledged, {cov['unaccountedCount']} unaccounted of {cov['total']})"
    )

    if cov["unaccounted"]:
        print("\n  unaccounted files (claim them, or list in entiendo/unclaimed.txt):")
        for f in cov["unaccounted"]:
            print(f"    ? {f}")

    if result.errors:
        print()
        for err in result.errors:
            print(f"  FAIL  {err}")
        print(f"\n✗ {len(result.errors)} reconciliation error(s)")
        return 1

    print("\n✓ graph reconciled — no drift")
    return 0
