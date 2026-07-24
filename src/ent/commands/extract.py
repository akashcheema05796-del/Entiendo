"""`ent extract` — L1. Emit graph.json + coverage.json; fail on drift.

STUB. Wired but not implemented — Phase 2 (L1) fills this in.

Planned behaviour:
  - static analysis of each node's claimed files → actual imports/calls
  - reconcile declared `dependencies` against reality (Invariant 5)
  - emit entiendo/graph.json and entiendo/coverage.json (generated artifacts)
  - exit non-zero on declared-vs-actual divergence, naming both nodes
"""

from __future__ import annotations

import argparse

from ._stub import not_implemented


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "extract",
        help="[L1] emit graph.json + coverage.json; fail on drift",
        description="Reconcile manifests against reality and emit the graph.",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="fail on drift without rewriting artifacts (CI mode)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    return not_implemented(
        command="extract",
        phase="Phase 2 (L1: Extractor & reconciler)",
        summary="Static-analyse claimed files, reconcile declared vs actual "
        "dependencies, emit graph.json + coverage.json.",
        acceptance="deliberately add an undeclared dependency → build fails naming "
        "both nodes. Coverage number is correct.",
    )
