"""The eval runner (Phase 7). tier0 executes the node; tier1 scores it.

**tier0** now *runs the node* over fixture rows in isolation (§2): dependency
calls are served from the fixture's stubs, and any unstubbed dependency call is an
I/O violation. For each row it checks the output against the contract schema and
evaluates the real invariants against the real output. Verdicts: GREEN / RED /
UNTESTED / ERROR (§5).

**tier1** executes the node `minRuns` times over a golden dataset with real I/O
permitted, scores each run with the declared metric, and judges the run
distribution against the baseline with the anti-flicker statistics of §7
(WITHIN_BAND / REGRESSED / IMPROVED / UNSTABLE), overlaying budget checks (§9,
DEGRADED). Blessing is enforced (§8): an unblessed or stale dataset runs
advisory-only.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .. import baselines, gitinfo, history, testing, tracing, trajectory, verdicts
from ..invariants import InvariantError, eval_invariant
from ..manifest import Node
from ..version import compute_version
from .entrypoint import (EntrypointDrift, EntrypointError, Harness, NoEntrypoint,
                         resolve_entrypoint, resolve_harness)


def _invoker(node: "Node", root: Path, entrypoint: Callable[..., Any]) -> Callable[[dict], Any]:
    """How a fixture row becomes a call.

    Default: `entrypoint(row["input"])` — one argument, the shape most units
    have. When the unit declares `contract.harness`, that adapter is handed the
    row plus a context (entrypoint, root, node) and returns the output instead.
    This is the seam for `f(node, root)`, `f(root, node_id)`, and class-based
    APIs that must be constructed before they can be called; without it those
    units are permanently UNTESTED.
    """
    harness = resolve_harness(node, root)
    if harness is None:
        return lambda row: entrypoint(row["input"])
    ctx = Harness(entrypoint, root, node)
    return lambda row: harness(row, ctx)
from .metrics import get_metric


@dataclass
class Check:
    type: str
    status: str  # "pass" | "fail" | "skip" | "error"
    detail: str


@dataclass
class EvalResult:
    node_id: str
    tier: int
    verdict: str
    duration_ms: float
    checks: list[Check] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    advisory: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not Path(path).exists():
        return rows
    for i, line in enumerate(Path(path).read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _tier0_fixtures(node: Node, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in node.raw.get("evals", {}).get("tier0", []):
        if entry.get("type") == "smoke" and entry.get("fixture"):
            for i, row in enumerate(load_rows(root / entry["fixture"])):
                row.setdefault("name", f"{entry['fixture']}#{i}")
                rows.append(row)
    return rows


def _run_trajectory(node: Node, root: Path) -> tuple[bool, list[Check]]:
    """Evaluate every `type: trajectory` tier0 entry against its run-log fixture.

    Returns (any_ran, checks). `any_ran` is True only if at least one trajectory
    actually evaluated (had a fixture) — so a unit whose only signal is a green
    trajectory reads GREEN, not UNTESTED. Falls back to `interior.maxSteps`.
    """
    entries = [e for e in node.raw.get("evals", {}).get("tier0", []) if e.get("type") == "trajectory"]
    if not entries:
        return False, []
    interior = node.raw.get("interior", {}) or {}
    registry = {t.get("name") for t in interior.get("tools", []) or [] if t.get("name")}
    default_max = interior.get("maxSteps")

    ran = False
    checks: list[Check] = []
    for entry in entries:
        fixture = entry.get("fixture")
        if not fixture:
            checks.append(Check("trajectory", "skip", "trajectory check has no run-log fixture"))
            continue
        rows = load_rows(Path(root) / fixture)
        if not rows:
            checks.append(Check("trajectory", "skip", f"trajectory fixture '{fixture}' missing/empty"))
            continue
        calls = trajectory.calls_from_log(rows)
        rule = dict(entry)
        if rule.get("maxSteps") is None and default_max is not None:
            rule["maxSteps"] = default_max
        passed, detail = trajectory.evaluate(rule, calls, registry)
        ran = True
        checks.append(Check("trajectory", "pass" if passed else "fail", detail))
    return ran, checks


# --------------------------------------------------------------------------- #
# tier0 — execution
# --------------------------------------------------------------------------- #

def run_tier0(node: Node, root: Path, *, entrypoint: Callable[..., Any] | None = None) -> EvalResult:
    root = Path(root)
    start = time.perf_counter()

    def done(verdict: str, checks: list[Check]) -> EvalResult:
        return EvalResult(node.id, 0, verdict, round((time.perf_counter() - start) * 1000, 3), checks)

    if node.raw.get("evals", {}).get("executionMode") == "skip":
        return done(verdicts.UNTESTED, [Check("execution", "skip", "executionMode: skip")])

    # --- trajectory checks (agentic units, §14.2): reason over the tool-call
    #     sequence from a run-log fixture. Deterministic, no execution. ---
    checks: list[Check] = []
    traj_ran, traj_checks = _run_trajectory(node, root)
    checks.extend(traj_checks)
    if any(c.status == "fail" for c in traj_checks):
        return done(verdicts.RED, checks)

    if entrypoint is None:
        try:
            entrypoint = resolve_entrypoint(node, root)
        except NoEntrypoint:
            if traj_ran:
                return done(verdicts.GREEN, checks)   # the trajectory tested the path
            return done(verdicts.UNTESTED, checks + [Check("entrypoint", "skip", "no contract.entrypoint")])
        except EntrypointDrift as exc:
            return done(verdicts.ERROR, checks + [Check("entrypoint", "error", str(exc))])
        except EntrypointError as exc:
            return done(verdicts.ERROR, checks + [Check("entrypoint", "error", str(exc))])

    rows = _tier0_fixtures(node, root)
    if not rows:
        if traj_ran:
            return done(verdicts.GREEN, checks)
        return done(verdicts.UNTESTED, checks + [Check("smoke", "skip", "entrypoint but no fixture rows")])

    contract = node.raw.get("contract", {})
    do_schema = any(e.get("type") == "schema_validation" for e in node.raw["evals"]["tier0"])
    do_invariants = any(e.get("type") == "invariant_check" for e in node.raw["evals"]["tier0"])

    try:
        invoke = _invoker(node, root, entrypoint)
    except EntrypointError as exc:
        return done(verdicts.ERROR, checks + [Check("harness", "error", str(exc))])

    for row in rows:
        name = row["name"]
        # --- execute in isolation ---
        try:
            with testing.stub(node, row):
                output = invoke(row)
        except (testing.Tier0IOViolation) as exc:
            checks.append(Check("isolation", "error",
                                f"TIER0_IO_VIOLATION on '{name}': reached unstubbed dependency "
                                f"'{exc}' — check the node's dependencies block"))
            return done(verdicts.ERROR, checks)
        except testing.Tier0QueueExhausted as exc:
            checks.append(Check("isolation", "error", f"queue exhausted on '{name}': {exc}"))
            return done(verdicts.ERROR, checks)
        except Exception as exc:
            expect_error = row.get("expectError")
            if expect_error and type(exc).__name__ == expect_error:
                checks.append(Check("expectError", "pass", f"'{name}': raised {expect_error} as expected"))
                continue
            checks.append(Check("execute", "fail",
                                f"'{name}': raised {type(exc).__name__}: {exc}"))
            return done(verdicts.RED, checks)

        if row.get("expectError"):
            checks.append(Check("expectError", "fail",
                                f"'{name}': expected {row['expectError']} but returned normally"))
            return done(verdicts.RED, checks)

        # --- schema ---
        if do_schema:
            err = _schema_check(contract, row["input"], output, node.path.parent)
            if err:
                checks.append(Check("schema_validation", "fail", f"'{name}': {err}"))
                return done(verdicts.RED, checks)

        # --- invariants (real evaluation) ---
        if do_invariants:
            for inv in contract.get("invariants", []) or []:
                try:
                    passed, detail = eval_invariant(inv, row["input"], output)
                except (InvariantError, Exception) as exc:
                    checks.append(Check("invariant_check", "fail",
                                        f"'{name}': invariant \"{inv}\" could not evaluate: {exc}"))
                    return done(verdicts.RED, checks)
                if not passed:
                    checks.append(Check("invariant_check", "fail",
                                        f"'{name}': invariant \"{inv}\" failed: {detail}"))
                    return done(verdicts.RED, checks)

        # --- expect (exact) ---
        if "expect" in row and output != row["expect"]:
            checks.append(Check("expect", "fail", f"'{name}': output != expected"))
            return done(verdicts.RED, checks)

        checks.append(Check("row", "pass", f"'{name}' ran, conforms, invariants hold"))

    return done(verdicts.GREEN, checks)


def _schema_check(contract: dict, inp: Any, output: Any, manifest_dir: Path) -> str | None:
    import jsonschema

    for side, value in (("input", inp), ("output", output)):
        spec = contract.get(side)
        if isinstance(spec, dict) and "$ref" in spec:
            target = (manifest_dir / spec["$ref"]).resolve()
            if not target.exists():
                return f"{side} $ref '{spec['$ref']}' not found"
            schema = json.loads(target.read_text())
            errs = sorted(jsonschema.Draft202012Validator(schema).iter_errors(value),
                          key=lambda e: list(e.path))
            if errs:
                return f"{side} does not conform: {errs[0].message}"
    return None


# --------------------------------------------------------------------------- #
# tier1 — golden runner (§6, §7, §8, §9)
# --------------------------------------------------------------------------- #

def run_tier1(node: Node, root: Path, *, entrypoint: Callable[..., Any] | None = None) -> EvalResult:
    root = Path(root)
    start = time.perf_counter()

    def done(verdict: str, checks: list[Check], stats: dict | None = None, advisory: bool = False) -> EvalResult:
        return EvalResult(node.id, 1, verdict, round((time.perf_counter() - start) * 1000, 3),
                          checks, stats or {}, advisory)

    golden = next((e for e in node.raw.get("evals", {}).get("tier1", []) if e.get("type") == "golden"), None)
    if golden is None:
        return done(verdicts.UNTESTED, [Check("golden", "skip", "no tier1 golden configured")])

    dataset_path = root / golden["dataset"] if golden.get("dataset") else None
    rows = load_rows(dataset_path) if dataset_path else []
    if not rows:
        return done(verdicts.ERROR, [Check("golden", "error", f"dataset '{golden.get('dataset')}' missing/empty")])
    if any("expect" not in r for r in rows):
        return done(verdicts.ERROR, [Check("golden", "error", "every golden row requires 'expect'")])

    # --- blessing (§8): gating only if manifest-blessed AND signature matches ---
    gating = golden.get("humanBlessed") is True and baselines.blessing_valid(root, node.id, dataset_path)
    advisory = not gating
    bless_note = ("blessed" if gating else
                  "ADVISORY — dataset not blessed or changed since blessing (run `ent bless`)")

    try:
        metric = get_metric(golden["metric"])
    except KeyError as exc:
        return done(verdicts.ERROR, [Check("golden", "error", str(exc))], advisory=advisory)

    if entrypoint is None:
        try:
            entrypoint = resolve_entrypoint(node, root)
        except NoEntrypoint:
            return done(verdicts.UNTESTED, [Check("entrypoint", "skip", "no contract.entrypoint")])
        except EntrypointError as exc:
            return done(verdicts.ERROR, [Check("entrypoint", "error", str(exc))], advisory=advisory)

    baseline_rec = baselines.read_baseline(root, node.id) or {}
    baseline = baseline_rec.get("baseline", golden.get("baseline"))
    min_runs = int(baseline_rec.get("minRuns", golden.get("minRuns", 1)))
    significance = float(baseline_rec.get("significance", golden.get("significance", 0.0)))

    run_scores: list[float] = []
    row_matrix: list[list[float]] = []       # per-run row scores → per-row means (v6 1.2)
    total_cost = 0.0
    latencies: list[float] = []
    try:
        invoke = _invoker(node, root, entrypoint)
    except EntrypointError as exc:
        return done(verdicts.ERROR, [Check("harness", "error", str(exc))], advisory=advisory)
    for _ in range(min_runs):
        with tracing.capture() as spans:
            row_scores = []
            for i, row in enumerate(rows):
                try:
                    out = invoke(row)
                except Exception as exc:
                    return done(verdicts.ERROR,
                                [Check("golden", "error", f"node raised on row {i}: {exc}")], advisory=advisory)
                row_scores.append(metric(out, row["expect"]))
        run_scores.append(_mean(row_scores))
        row_matrix.append(row_scores)
        total_cost += sum(s.cost_usd or 0.0 for s in spans)
        latencies.extend(s.duration_ms for s in spans if s.node_id == node.id)

    # per-row means across the minRuns runs — the paired sample the bootstrap uses
    row_means = [round(_mean([run[i] for run in row_matrix]), 6) for i in range(len(rows))]

    mean = _mean(run_scores)
    spread = statistics.stdev(run_scores) if len(run_scores) > 1 else 0.0
    p95 = _percentile(latencies, 95) if latencies else 0.0
    cost_per_call = total_cost / (min_runs * len(rows)) if rows else 0.0

    stats = {
        "runs": [round(s, 4) for s in run_scores], "mean": round(mean, 4),
        "spread": round(spread, 4), "baseline": baseline, "n": min_runs,
        "metric": golden["metric"], "p95LatencyMs": round(p95, 1),
        "costUsd": round(total_cost, 4), "blessed": gating,
        "compositeVersion": compute_version(node, root)["composite"],
    }

    # v6 1.2 — a real statistical test when the baseline carries per-row scores;
    # otherwise the legacy threshold, tagged so nobody mistakes it for a test.
    base_rows = baseline_rec.get("rowScores")
    if base_rows and len(base_rows) == len(row_means):
        verdict, detail, boot = _bootstrap_verdict(row_means, base_rows, significance)
        stats.update(boot)
    else:
        verdict, detail = _stat_verdict(mean, baseline, spread, significance)
        stats["verdictMethod"] = "threshold-legacy"
    stats["rowScores"] = row_means
    stats["delta"] = round(mean - baseline, 4) if baseline is not None else None

    # baseline proposal on improvement (§7 — never automatic)
    if verdict == verdicts.IMPROVED or baseline is None:
        baselines.write_pending(root, node.id, {
            "baseline": round(mean, 4), "metric": golden["metric"],
            "minRuns": min_runs, "significance": significance,
            "rowScores": row_means,          # the paired sample for future bootstraps
        })
        detail += " — baseline proposal written (ent baseline accept)"

    # budgets (§9): correct-but-slow/expensive → DEGRADED (unless already red)
    budget_note = _budget_check(node.raw.get("budgets", {}), p95, cost_per_call)
    if budget_note and verdict not in (verdicts.REGRESSED,):
        verdict = verdicts.DEGRADED
        detail += f" — {budget_note}"

    checks = [Check("golden", "pass" if verdict in (verdicts.WITHIN_BAND, verdicts.IMPROVED) else
                    "fail" if verdict == verdicts.REGRESSED else "skip",
                    f"{golden['metric']}={mean:.4f} n={min_runs} spread={spread:.4f} "
                    f"baseline={baseline} → {verdict} [{bless_note}] {detail}")]

    _record_eval(root, node, stats, verdict, min_runs)
    return done(verdict, checks, stats, advisory)


_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_SEED = 20260803        # fixed — verdicts must be reproducible


def _bootstrap_verdict(new_rows: list[float], base_rows: list[float],
                       sig: float) -> tuple[str, str, dict[str, Any]]:
    """Paired bootstrap over golden rows (v6 1.2) — a test, not a threshold.

    Per row, d_i = new_i − base_i. Resample rows with replacement
    (10k, fixed seed) → a 95% CI on mean(d). REGRESSED iff the CI is entirely
    below zero; IMPROVED iff entirely above; straddling zero is WITHIN_BAND when
    the point estimate is inside `significance`, UNSTABLE when the CI half-width
    exceeds it (too noisy to judge at this n).
    """
    import random

    diffs = [n - b for n, b in zip(new_rows, base_rows)]
    n = len(diffs)
    mean_d = _mean(diffs)
    rng = random.Random(_BOOTSTRAP_SEED)
    means = sorted(
        _mean([diffs[rng.randrange(n)] for _ in range(n)])
        for _ in range(_BOOTSTRAP_RESAMPLES))
    lo = means[int(0.025 * _BOOTSTRAP_RESAMPLES)]
    hi = means[int(0.975 * _BOOTSTRAP_RESAMPLES) - 1]
    half_width = (hi - lo) / 2.0
    boot = {"verdictMethod": "paired-bootstrap", "ciLow": round(lo, 4),
            "ciHigh": round(hi, 4), "nRows": n,
            # the smallest effect this n could have called — honesty about power
            "minDetectableEffect": round(half_width, 4)}

    ci_txt = f"Δ={mean_d:+.4f} CI95[{lo:+.4f},{hi:+.4f}] n={n}"
    if hi < 0:
        return verdicts.REGRESSED, f"{ci_txt} — CI entirely below zero", boot
    if lo > 0:
        return verdicts.IMPROVED, f"{ci_txt} — CI entirely above zero", boot
    if abs(mean_d) <= sig and half_width <= sig:
        return verdicts.WITHIN_BAND, f"{ci_txt} — within significance {sig}", boot
    if half_width > sig:
        return verdicts.UNSTABLE, f"{ci_txt} — CI half-width {half_width:.4f} > {sig}: underpowered at n={n}", boot
    return verdicts.WITHIN_BAND, f"{ci_txt} — straddles zero", boot


def _stat_verdict(mean: float, baseline: float | None, spread: float, sig: float) -> tuple[str, str]:
    if baseline is None:
        return verdicts.WITHIN_BAND, "no baseline yet"
    delta = mean - baseline
    if abs(delta) <= sig:
        return verdicts.WITHIN_BAND, f"delta={delta:+.4f} within significance {sig}"
    if delta < 0 and abs(delta) > spread:
        return verdicts.REGRESSED, f"delta={delta:+.4f} exceeds spread {spread:.4f}"
    if delta > 0 and abs(delta) > spread:
        return verdicts.IMPROVED, f"delta={delta:+.4f} exceeds spread {spread:.4f}"
    return verdicts.UNSTABLE, f"delta={delta:+.4f} within run-to-run spread {spread:.4f} — too noisy to judge"


def _budget_check(budgets: dict, p95: float, cost_per_call: float) -> str | None:
    over = []
    if budgets.get("p95LatencyMs") is not None and p95 > budgets["p95LatencyMs"]:
        over.append(f"p95 {p95:.0f}ms > {budgets['p95LatencyMs']}ms")
    if budgets.get("costPerCallUsd") is not None and cost_per_call > budgets["costPerCallUsd"]:
        over.append(f"cost ${cost_per_call:.4f} > ${budgets['costPerCallUsd']}")
    return "over budget: " + "; ".join(over) if over else None


def _record_eval(root: Path, node: Node, stats: dict, verdict: str, n: int) -> None:
    row = {"ts": gitinfo.now_iso(), "nodeId": node.id, "tier": 1, "verdict": verdict, **stats}
    path = Path(root) / "entiendo" / "history" / "evals.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


# --------------------------------------------------------------------------- #
# tier2 — LLM judge (scaffold; out of Phase 7 scope, kept working)
# --------------------------------------------------------------------------- #

def run_tier2(
    node: Node,
    root: Path,
    *,
    judge: Callable[[Any, Any, str], float] | None = None,
    entrypoint: Callable[..., Any] | None = None,
) -> EvalResult:
    """Rubric-driven LLM judge over a sample. Without a judge it skips — never faked."""
    root = Path(root)
    start = time.perf_counter()
    conf = next((e for e in node.raw.get("evals", {}).get("tier2", []) if e.get("type") == "llm_judge"), None)

    def done(verdict: str, checks: list[Check]) -> EvalResult:
        return EvalResult(node.id, 2, verdict, round((time.perf_counter() - start) * 1000, 3), checks)

    if conf is None:
        return done(verdicts.UNTESTED, [Check("llm_judge", "skip", "no tier2 llm_judge configured")])
    rubric_path = root / conf["rubric"] if conf.get("rubric") else None
    if rubric_path is None or not rubric_path.exists():
        return done(verdicts.ERROR, [Check("llm_judge", "error", f"rubric '{conf.get('rubric')}' not found")])
    rubric = rubric_path.read_text()
    if judge is None:
        return done(verdicts.UNTESTED, [Check("llm_judge", "skip",
                    "no judge configured — the LLM judge is expensive; wire one via run_tier2(judge=...)")])

    golden = next((e for e in node.raw.get("evals", {}).get("tier1", []) if e.get("type") == "golden"), None)
    dataset = load_rows(root / golden["dataset"]) if golden and golden.get("dataset") else []
    if not dataset:
        return done(verdicts.UNTESTED, [Check("llm_judge", "skip", "no sample inputs (needs a tier1 golden dataset)")])

    if entrypoint is None:
        try:
            entrypoint = resolve_entrypoint(node, root)
        except EntrypointError as exc:
            return done(verdicts.UNTESTED, [Check("llm_judge", "skip", f"node not runnable: {exc}")])

    sample = dataset[: int(conf.get("sampleSize", len(dataset)))]
    scores = []
    try:
        invoke = _invoker(node, root, entrypoint)
    except EntrypointError as exc:
        return done(verdicts.UNTESTED, [Check("llm_judge", "skip", f"harness: {exc}")])
    for i, row in enumerate(sample):
        try:
            out = invoke(row)
        except Exception as exc:
            return done(verdicts.ERROR, [Check("llm_judge", "error", f"node raised on sample row {i}: {exc}")])
        scores.append(float(judge(row["input"], out, rubric)))

    avg = _mean(scores)
    verdict = verdicts.GREEN if avg >= 3.0 else verdicts.RED
    status = "pass" if avg >= 3.0 else "fail"
    return done(verdict, [Check("llm_judge", status, f"mean judge score {avg:.2f}/5 over {len(sample)} sample(s)")])


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _percentile(xs: list[float], p: int) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
