"""`ent ci` — one command: validate + reconcile + eval, one pass/fail.

The single step a CI job or a pre-commit hook runs. Wraps the three gates that
already exist so you don't wire three commands and three exit codes.

Exit codes (Phase 7 severity table, max across stages — v6 3.2):
  0  all gates pass / within band
  1  RED unit or a REGRESSED blessed golden
  2  ERROR (harness failure, invalid manifest, drift) or deps missing
  4  UNSTABLE / DEGRADED blessed golden (too noisy to judge, or over budget)
Unblessed goldens are advisory — they never block.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..ci import run_ci, summary_lines


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "ci",
        help="run validate + reconcile + eval as one pass/fail gate (CI / pre-commit)",
        description="The one gate for CI: manifests valid, graph reconciles, no RED units.",
    )
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument("--soft", action="store_true",
                   help="treat reconcile drift as a warning (progressive adoption)")
    p.add_argument("--min-coverage", type=float, default=None, metavar="PCT",
                   help="also fail if claimed+acknowledged coverage is below PCT%%")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        result = run_ci(root, soft=args.soft,
                        min_coverage=getattr(args, "min_coverage", None))
    except ModuleNotFoundError as exc:
        print(f"ent ci: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    print("entiendo ci\n")
    for line in summary_lines(result):
        print(line)
    return result.exit_code
