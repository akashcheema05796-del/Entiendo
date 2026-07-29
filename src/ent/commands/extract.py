"""`ent extract` — L1. Emit graph.json + coverage.json; fail on drift.

Runs the reconciler over the project and writes the two generated artifacts.
Validates manifests first (L0) — a graph built from invalid manifests is
meaningless. Exits non-zero on drift, double-claims, or dangling dependencies,
naming both nodes (Invariant 5).

`--soft` is for a repo mid-migration: drift (undeclared edges) is reported as a
warning and the build passes, while structural errors (double-claim, unknown-node
dependency, entrypoint drift) still fail. Ramp coverage without a red build, then
drop `--soft` once the graph is honest.

Exit codes:
  0  clean — artifacts written, no drift (or --soft with drift-only)
  1  drift / structural error (in --soft, only structural fails)
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
    p.add_argument(
        "--soft",
        action="store_true",
        help="report drift as warnings instead of failing the build "
             "(progressive adoption); structural errors still fail",
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
        drift, structural = result.partition_errors()
        print()
        # In soft mode, drift is a warning and structural errors still fail. In
        # default mode everything is a failure (unchanged behaviour).
        for err in structural:
            print(f"  FAIL  {err}")
        for err in drift:
            print(f"  {'WARN' if args.soft else 'FAIL'}  {err}")

        if structural or not args.soft:
            failed = len(result.errors) if not args.soft else len(structural)
            print(f"\n✗ {failed} reconciliation error(s)")
            return 1

        print(f"\n⚠ {len(drift)} drift warning(s) — soft mode, build not failed "
              "(declare them to make the graph honest)")
        return 0

    print("\n✓ graph reconciled — no drift")
    return 0
