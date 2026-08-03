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
    p.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        metavar="PCT",
        help="fail if claimed+acknowledged coverage is below PCT%% (ramp target)",
    )
    p.add_argument(
        "--with-spans",
        nargs="?",
        const="__project__",
        default=None,
        metavar="PATH",
        help="verify declared edges from recorded spans (default: the project's "
             "own history; or pass an events.jsonl path)",
    )
    p.set_defaults(handler=_run)


def _observed_spans(root: Path, with_spans: str | None):
    """Resolve --with-spans to an observed-edge map, or None when not requested."""
    if with_spans is None:
        return None
    from .. import spans as spans_mod
    if with_spans == "__project__":
        return spans_mod.observe_root(root)
    return spans_mod.observe_path(Path(with_spans))


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    try:
        report = validate_root(root)
        if not report.ok:
            print("ent extract: manifests are invalid — run `ent validate` first.")
            return 2
        observed = _observed_spans(root, getattr(args, "with_spans", None))
        result = extract(root, spans=observed)
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

    # v6 3.5 — blind-spot warnings: constructs static analysis cannot see.
    # Advisory only; absence of an edge is not proof of no dependency.
    blind = graph.get("possibleUndeclaredDynamicDep", [])
    if blind:
        print("\n  possible undeclared dynamic deps (static analysis is blind here):")
        for w in blind:
            print(f"    ? {w['node']}: {w['file']} uses {w['pattern']}")

    # V1: declared edges no span has confirmed yet (only when --with-spans ran).
    unverified = graph.get("unverifiedDeclaredEdges", [])
    if getattr(args, "with_spans", None) is not None and unverified:
        print("\n  declared but never observed in a span (tentative):")
        for u in unverified:
            print(f"    ~ {u['from']} -> {u['to']} ({'/'.join(u['kinds'])})")

    # coverage ramp target (--min-coverage): a threshold a migrating team raises.
    min_cov = getattr(args, "min_coverage", None)
    cov_pct = cov["coverage"] * 100.0
    below = min_cov is not None and cov_pct + 1e-9 < min_cov

    def _coverage_line() -> None:
        if below:
            print(f"✗ coverage {cov_pct:.0f}% is below the --min-coverage "
                  f"{min_cov:.0f}% target")

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
            _coverage_line()
            return 1

        print(f"\n⚠ {len(drift)} drift warning(s) — soft mode, build not failed "
              "(declare them to make the graph honest)")
        if below:
            print()
            _coverage_line()
            return 1
        return 0

    if below:
        print()
        _coverage_line()
        return 1

    print("\n✓ graph reconciled — no drift")
    return 0
