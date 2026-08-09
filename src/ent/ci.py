"""`ent ci` — the one gate a CI job or pre-commit hook calls (gap analysis §4).

Individually the checks already exist (`validate`, `extract --check`, `eval
--all`); wiring three commands and reasoning about three exit codes is the
friction. `run_ci` runs all three, reports a stage line each, and collapses them
to a single pass/fail — the thing you put in one CI step or a pre-commit hook.

Pure `run_ci(root) -> CiResult` so it is tested without a subprocess; the CLI
prints the stages and returns `exit_code`. `--soft` passes through to the
reconcile stage (drift → warning) for a repo mid-migration.

Exit codes follow the Phase 7 severity table (verdicts.EXIT_CODE), and the
result is the MAX severity across stages (v6 3.2):

    0  pass / within-band
    1  RED / REGRESSED         (a check failed, a blessed golden regressed)
    2  ERROR                   (harness failure, invalid manifest, drift)
    4  UNSTABLE / DEGRADED     (too noisy to judge, or over budget)

The tier1 stage gates on BLESSED goldens only — an unblessed or stale dataset
is advisory and never blocks (§8: gating power comes from a human having looked
at the rows, never from the AI's own data).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Stage:
    name: str
    ok: bool
    detail: str
    warnings: list[str] = field(default_factory=list)
    # Explicit exit severity (verdicts.EXIT_CODE). None → derived: 0 if ok else 1,
    # so pre-v6 stages keep their pass/fail behaviour unchanged.
    severity: int | None = None

    @property
    def exit_severity(self) -> int:
        if self.severity is not None:
            return self.severity
        return 0 if self.ok else 1


@dataclass
class CiResult:
    stages: list[Stage]

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.stages)

    @property
    def exit_code(self) -> int:
        # Max severity across stages — a REGRESSED golden (1) and an UNSTABLE
        # one (4) exit 4; one flat pass/fail bit would hide the distinction.
        return max((s.exit_severity for s in self.stages), default=0)


def run_ci(root: Path, *, soft: bool = False, min_coverage: float | None = None) -> CiResult:
    """Run validate → reconcile (→ coverage) → eval → tier1, exit = max severity."""
    from .extractor import extract

    root = Path(root)
    ext = extract(root)                                 # once, shared by reconcile + coverage
    stages = [_validate_stage(root), _reconcile_stage(ext, soft=soft)]
    if min_coverage is not None:
        stages.append(_coverage_stage(ext, min_coverage))
    stages.append(_eval_stage(root))
    stages.append(_tier1_stage(root))
    stages.append(_budget_stage(root))
    return CiResult(stages=stages)


def _validate_stage(root: Path) -> Stage:
    from .validation import validate_root
    report = validate_root(root)
    n = len(report.results)
    if report.ok:
        return Stage("validate", True, f"{n} manifest(s) valid")
    bad = sum(1 for r in report.results if getattr(r, "errors", None))
    return Stage("validate", False, f"{bad} of {n} manifest(s) invalid — run `ent validate`")


def _reconcile_stage(result: Any, *, soft: bool) -> Stage:
    cov = result.coverage.get("coverage")
    cov_txt = f"coverage {cov:.0%}" if cov is not None else "coverage n/a"
    if result.ok:
        return Stage("reconcile", True, f"no drift, {cov_txt}")
    drift, structural = result.partition_errors()
    if soft and not structural:
        return Stage("reconcile", True, f"{cov_txt}, {len(drift)} drift warning(s) (soft)",
                     warnings=drift)
    failing = structural + (drift if not soft else [])
    return Stage("reconcile", False,
                 f"{len(failing)} reconciliation error(s) — run `ent extract`"
                 + (" --soft" if soft else ""),
                 warnings=drift if soft else [])


def _coverage_stage(result: Any, min_coverage: float) -> Stage:
    cov = (result.coverage.get("coverage") or 0.0) * 100.0
    if cov + 1e-9 >= min_coverage:
        return Stage("coverage", True, f"{cov:.0f}% (>= {min_coverage:.0f}% target)")
    return Stage("coverage", False, f"{cov:.0f}% below the {min_coverage:.0f}% target")


def _eval_stage(root: Path) -> Stage:
    from . import verdicts
    from .evals.runner import run_tier0
    from .manifest import Node, discover, load

    counts: dict[str, int] = {verdicts.GREEN: 0, verdicts.RED: 0,
                              verdicts.UNTESTED: 0, verdicts.ERROR: 0}
    failing: list[str] = []
    for path in discover(root):
        node = Node.from_manifest(load(path), path)
        verdict = run_tier0(node, root).verdict
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict in (verdicts.RED, verdicts.ERROR):
            failing.append(f"{node.id}:{verdict}")

    summary = (f"{counts[verdicts.GREEN]} green, {counts[verdicts.UNTESTED]} untested, "
               f"{counts[verdicts.RED]} red, {counts[verdicts.ERROR]} error")
    if failing:
        severity = 2 if counts[verdicts.ERROR] else 1     # ERROR outranks RED (v6 3.2)
        return Stage("eval", False, f"{summary} — {', '.join(failing)}", severity=severity)
    return Stage("eval", True, summary)


def _budget_stage(root: Path) -> Stage:
    """Declared budgets vs measured reality (research rec C).

    `tokensPerCall` / `costPerCallUsd` / `p95LatencyMs` were declared but never
    enforced — dead schema fields. Measurements come from recorded traces
    (manual capture or the OTel gen_ai reader); a unit over any declared budget
    is DEGRADED (severity 4), the same lane as UNSTABLE: not broken, but not
    within its own declaration either. Units with no declared budgets or no
    measurements simply pass — partial coverage is the normal state.
    """
    from . import history, verdicts
    from .manifest import Node, discover, load
    from .render import _measured_budgets

    measured = _measured_budgets(history.traces(root))
    over: list[str] = []
    checked = 0
    for path in discover(root):
        node = Node.from_manifest(load(path), path)
        declared = (node.raw.get("budgets") or {})
        m = measured.get(node.id)
        if not declared or not m:
            continue
        checked += 1
        pairs = (("tokensPerCall", m.get("avgTokens"), "tokens/call"),
                 ("costPerCallUsd", m.get("avgCostUsd"), "$/call"),
                 ("p95LatencyMs", m.get("p95LatencyMs"), "ms p95"))
        for key, got, label in pairs:
            limit = declared.get(key)
            if limit is not None and got is not None and got > limit:
                over.append(f"{node.id}: {got} > {limit} {label}")
    if over:
        return Stage("budgets", False,
                     f"{len(over)} unit(s) over declared budget",
                     warnings=over, severity=verdicts.EXIT_CODE[verdicts.DEGRADED])
    return Stage("budgets", True,
                 f"{checked} unit(s) within declared budgets" if checked
                 else "no declared budgets with measurements")


def _tier1_stage(root: Path) -> Stage:
    """Golden runs on BLESSED datasets only (v6 3.2).

    An unblessed or content-drifted dataset never blocks — it is counted as
    advisory and not even executed here (tier1 permits real I/O; CI spends that
    only where a human has signed the rows). Severity per verdict comes from
    verdicts.EXIT_CODE and the stage carries the max.
    """
    from . import baselines, verdicts
    from .evals.runner import run_tier1
    from .manifest import Node, discover, load

    gated: list[str] = []
    advisory = 0
    severity = 0
    for path in discover(root):
        node = Node.from_manifest(load(path), path)
        golden = next((e for e in node.raw.get("evals", {}).get("tier1", [])
                       if e.get("type") == "golden"), None)
        if golden is None:
            continue
        dataset = Path(root) / golden["dataset"] if golden.get("dataset") else None
        blessed = (golden.get("humanBlessed") is True and dataset is not None
                   and baselines.blessing_valid(root, node.id, dataset))
        if not blessed:
            advisory += 1
            continue
        verdict = run_tier1(node, root).verdict
        severity = max(severity, verdicts.exit_code(verdict))
        gated.append(f"{node.id}:{verdict}")

    if not gated and not advisory:
        return Stage("tier1", True, "no goldens configured")
    parts = []
    if gated:
        parts.append(f"{len(gated)} blessed golden(s) — {', '.join(gated)}")
    if advisory:
        parts.append(f"{advisory} advisory (unblessed — never blocks)")
    return Stage("tier1", severity == 0, "; ".join(parts), severity=severity)


def summary_lines(result: CiResult) -> list[str]:
    """Human-readable stage lines + a headline — shared by the CLI."""
    mark = {True: "✓", False: "✗"}
    lines = [f"  {mark[s.ok]} {s.name.ljust(9)}  {s.detail}" for s in result.stages]
    for s in result.stages:
        for w in s.warnings:
            lines.append(f"      ⚠ {w}")
    lines.append("")
    code = result.exit_code
    lines.append("✓ ent ci passed" if result.ok else f"✗ ent ci failed (exit {code})")
    return lines
