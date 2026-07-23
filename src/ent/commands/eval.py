"""`ent eval <node>` — L2. Run a node's evals.

STUB. Wired but not implemented — Phase 3 (L2) fills this in.

Planned behaviour:
  - tier0 by default: schema_validation + invariant_check + smoke, sub-second
  - --tier1 for golden datasets (minRuns + significance; humanBlessed required)
  - --tier2 for the LLM judge (nightly / on demand)
  - verdict judged against baseline with a significance threshold (Invariant 7)
"""

from __future__ import annotations

import argparse

from ._stub import not_implemented


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
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    return not_implemented(
        command="eval",
        phase="Phase 3 (L2: Instrumentation + eval runner)",
        summary="Run tiered evals for a node; tier0 verdict returns in <2s.",
        acceptance="one real request produces spans mapped to node IDs; "
        "`ent eval <node>` returns tier0 verdict in <2s.",
    )
