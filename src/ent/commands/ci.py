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
    p.add_argument("--enqueue-failures", action="store_true",
                   help="turn each RED/ERROR unit into a steering task the operator "
                        "loop can pick up (the judge diagnoses and delegates — it "
                        "never edits)")
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

    if getattr(args, "enqueue_failures", False):
        enqueued = _enqueue_failures(root, result)
        if enqueued:
            print(f"\n  → {len(enqueued)} failure(s) queued for the builder "
                  "(`await_steering` hands them to the operator loop)")
            for rid, unit in enqueued:
                print(f"    {rid}  {unit}")
    return result.exit_code


# --------------------------------------------------------------------------- #
# the steering bridge (astrobee gap 6)
# --------------------------------------------------------------------------- #
#
# Red verdicts used to be report lines; report lines cannot be delegated.
# This turns each RED/ERROR unit into a structured steering task the operator
# loop consumes through the normal Bridge (`await_steering` → edit through
# the unit → `post_verdict`). The separation holds the whole way: the judge
# diagnoses and DELEGATES — it never edits — and the re-run gate judges a fix
# it did not write. Tasks are mechanical only: entrypoints, requires,
# harnesses, dependency declarations. NEVER golden authorship — the builder
# must not write the answers it is graded against (that blessing stays
# human, SPEC §17).

def _remediation(root: Path, unit: str, verdict: str, detail: str) -> str:
    """One precise instruction: the failure, then mechanical options ranked."""
    import re

    from ..manifest import find_node
    from ..retrofit import _PROBE_MAX_CANDIDATES, _entrypoint_candidates, probe_entrypoint

    lines = [f"tier0 {verdict}: {detail or 'a check failed'}"]
    options: list[str] = []

    missing = re.search(r"No module named '([A-Za-z0-9_.]+)'", detail or "")
    if missing:
        top = missing.group(1).split(".")[0]
        options.append(
            f"declare `contract.requires: [{top}]` so this reads ENV-BLOCKED "
            "wherever that runtime is absent (honest, zero-risk)")

    node = find_node(root, unit)
    if node is not None and verdict == "ERROR":
        claimed = [root / c for c in node.claims if str(c).endswith(".py")]
        for spec in _entrypoint_candidates(unit, claimed, root)[:_PROBE_MAX_CANDIDATES]:
            if probe_entrypoint(root, spec) is None:
                options.append(
                    f"repoint contract.entrypoint at `{spec}` — probed, it "
                    "imports in this environment (add fixture rows for it)")
                break

    options.append("fix the unit itself if the failure is a genuine defect")
    for i, opt in enumerate(options):
        lines.append(f"option {chr(97 + i)}) {opt}")
    lines.append("Edit through the unit (apply_edit honours claims). Do NOT "
                 "author or bless golden datasets for this unit — ground "
                 "truth stays human (SPEC §17).")
    return "\n".join(lines)


def _enqueue_failures(root: Path, result) -> list[tuple[str, str]]:
    from .. import steering

    eval_stage = next((s for s in result.stages if s.name == "eval"), None)
    if eval_stage is None or not eval_stage.failures:
        return []
    already = {r.get("unit") for r in steering.pending(root)
               if str(r.get("instruction", "")).startswith("tier0 ")}
    out: list[tuple[str, str]] = []
    for failure in eval_stage.failures:
        unit = failure["unit"]
        if unit in already:
            continue                     # idempotent — one live task per unit
        instruction = _remediation(root, unit, failure["verdict"], failure["detail"])
        request = steering.enqueue(root, unit, instruction)
        out.append((request["id"], unit))
    return out
