"""L2 — tier0 eval runner.

Runs the deterministic, sub-second checks that gate every edit (SPEC.md §5.1).
Each check type is driven by the node's `evals.tier0` manifest entries:

  - schema_validation  contract input/output $ref schemas are valid JSON Schema,
                       and every smoke fixture `input` conforms to the input schema
  - invariant_check    every `contract.invariants` expression is well-formed
  - smoke              the fixture exists and every row parses as JSON

These are static — they do not execute node code, so they stay deterministic and
fast (the whole point of tier0). Runtime invariant enforcement rides on the spans
from the instrumentation layer and lands with the health lens.

tier1 (golden datasets) and tier2 (LLM judge) DO execute the node — they are the
more expensive tiers (SPEC.md §5.1). tier1 replays the node `minRuns` times over
a golden dataset, scores with the declared metric, and judges the mean against
the baseline with a significance threshold: **red only on statistically
meaningful regression** (§5.3), everything else is "within band". tier2 samples
rows and scores them with an LLM judge against a rubric.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..manifest import Node
from .entrypoint import EntrypointError, resolve_entrypoint
from .metrics import get_metric


@dataclass
class Check:
    type: str
    status: str  # "pass" | "fail" | "skip"
    detail: str


@dataclass
class EvalResult:
    node_id: str
    tier: int
    verdict: str  # "green" | "red"
    duration_ms: float
    checks: list[Check] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_tier0(node: Node, root: Path) -> EvalResult:
    """Run the node's tier0 checks and return a verdict."""
    root = Path(root)
    tier0 = node.raw.get("evals", {}).get("tier0", []) or []
    start = time.perf_counter()

    checks: list[Check] = []
    for entry in tier0:
        kind = entry.get("type")
        if kind == "schema_validation":
            checks.append(_check_schema(node, root))
        elif kind == "invariant_check":
            checks.append(_check_invariants(node))
        elif kind == "smoke":
            checks.append(_check_smoke(node, root, entry.get("fixture")))
        else:  # pragma: no cover - schema forbids unknown types
            checks.append(Check(kind or "?", "skip", "unknown tier0 check type"))

    if not checks:
        # No node without a tier-0 eval (Invariant 3) — surface the gap as red.
        checks.append(Check("tier0", "fail", "node declares no tier0 evals (Invariant 3)"))

    verdict = "red" if any(c.status == "fail" for c in checks) else "green"
    duration_ms = (time.perf_counter() - start) * 1000.0
    return EvalResult(node.id, 0, verdict, round(duration_ms, 3), checks)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    rows = []
    for _, row in _iter_rows(path):
        if row is not _BAD_ROW and isinstance(row, dict):
            rows.append(row)
    return rows


def run_tier1(node: Node, root: Path, *, entrypoint: Callable[..., Any] | None = None) -> EvalResult:
    """Golden-dataset scoring: replay minRuns times, judge mean vs baseline (§5.3)."""
    root = Path(root)
    start = time.perf_counter()
    golden = next(
        (e for e in node.raw.get("evals", {}).get("tier1", []) if e.get("type") == "golden"),
        None,
    )

    def done(checks: list[Check]) -> EvalResult:
        verdict = "red" if any(c.status == "fail" for c in checks) else "green"
        return EvalResult(node.id, 1, verdict, round((time.perf_counter() - start) * 1000, 3), checks)

    if golden is None:
        return done([Check("golden", "skip", "no tier1 golden configured")])
    if golden.get("humanBlessed") is not True:
        return done([Check("golden", "fail", "golden dataset requires humanBlessed: true (§5.2)")])

    dataset = _load_dataset(root / golden["dataset"]) if golden.get("dataset") else []
    if not dataset:
        return done([Check("golden", "fail", f"dataset '{golden.get('dataset')}' missing or empty")])

    try:
        metric = get_metric(golden["metric"])
    except KeyError as exc:
        return done([Check("golden", "fail", str(exc))])

    fn = entrypoint
    if fn is None:
        try:
            fn = resolve_entrypoint(node, root)
        except EntrypointError as exc:
            return done([Check("golden", "skip", f"node not runnable: {exc}")])

    min_runs = int(golden.get("minRuns", 1))
    significance = float(golden.get("significance", 0.0))
    baseline = golden.get("baseline")

    run_means: list[float] = []
    for _ in range(min_runs):
        row_scores = []
        for i, row in enumerate(dataset):
            try:
                out = fn(row["input"])
            except Exception as exc:
                return done([Check("golden", "fail", f"node raised on dataset row {i}: {exc}")])
            row_scores.append(metric(out, row.get("expected", {})))
        run_means.append(_mean(row_scores))

    score = _mean(run_means)
    detail = f"{golden['metric']}={score:.4f} over {min_runs} run(s)"
    if baseline is not None:
        delta = score - baseline
        detail += f", baseline={baseline}, delta={delta:+.4f} (sig={significance})"
        if delta < -significance:
            return done([Check("golden", "fail", f"regression — {detail}")])
        detail += " — within band"
    return done([Check("golden", "pass", detail)])


def run_tier2(
    node: Node,
    root: Path,
    *,
    judge: Callable[[Any, Any, str], float] | None = None,
    entrypoint: Callable[..., Any] | None = None,
) -> EvalResult:
    """LLM-judge scoring against a rubric over a sample (§5.1). Needs a judge callable.

    `judge(input, output, rubric) -> score in [1, 5]`. Without a judge the tier is
    skipped (the LLM judge is expensive and must be wired explicitly), never faked.
    """
    root = Path(root)
    start = time.perf_counter()
    conf = next(
        (e for e in node.raw.get("evals", {}).get("tier2", []) if e.get("type") == "llm_judge"),
        None,
    )

    def done(checks: list[Check]) -> EvalResult:
        verdict = "red" if any(c.status == "fail" for c in checks) else "green"
        return EvalResult(node.id, 2, verdict, round((time.perf_counter() - start) * 1000, 3), checks)

    if conf is None:
        return done([Check("llm_judge", "skip", "no tier2 llm_judge configured")])

    rubric_path = root / conf["rubric"] if conf.get("rubric") else None
    if rubric_path is None or not rubric_path.exists():
        return done([Check("llm_judge", "fail", f"rubric '{conf.get('rubric')}' not found")])
    rubric = rubric_path.read_text()

    if judge is None:
        return done([Check("llm_judge", "skip",
                           "no judge configured — the LLM judge is expensive; wire one via run_tier2(judge=...)")])

    # Sample inputs from the tier1 golden dataset (the available labelled inputs).
    golden = next((e for e in node.raw.get("evals", {}).get("tier1", []) if e.get("type") == "golden"), None)
    dataset = _load_dataset(root / golden["dataset"]) if golden and golden.get("dataset") else []
    if not dataset:
        return done([Check("llm_judge", "skip", "no sample inputs (needs a tier1 golden dataset)")])

    fn = entrypoint
    if fn is None:
        try:
            fn = resolve_entrypoint(node, root)
        except EntrypointError as exc:
            return done([Check("llm_judge", "skip", f"node not runnable: {exc}")])

    sample = dataset[: int(conf.get("sampleSize", len(dataset)))]
    scores = []
    for i, row in enumerate(sample):
        try:
            out = fn(row["input"])
        except Exception as exc:
            return done([Check("llm_judge", "fail", f"node raised on sample row {i}: {exc}")])
        scores.append(float(judge(row["input"], out, rubric)))

    avg = _mean(scores)
    status = "pass" if avg >= 3.0 else "fail"
    return done([Check("llm_judge", status, f"mean judge score {avg:.2f}/5 over {len(sample)} sample(s)")])


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #

def _load_json_schema(ref: str, manifest_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    target = (manifest_dir / ref).resolve()
    if not target.exists():
        return None, f"$ref '{ref}' not found"
    try:
        return json.loads(target.read_text()), None
    except json.JSONDecodeError as exc:
        return None, f"$ref '{ref}' is not valid JSON: {exc}"


def _check_schema(node: Node, root: Path) -> Check:
    import jsonschema  # lazy

    manifest_dir = node.path.parent
    contract = node.raw.get("contract", {})
    schemas: dict[str, Any] = {}

    # 1. contract schemas load + are valid JSON Schema
    for side in ("input", "output"):
        spec = contract.get(side)
        if isinstance(spec, dict) and "$ref" in spec:
            schema, err = _load_json_schema(spec["$ref"], manifest_dir)
            if err:
                return Check("schema_validation", "fail", err)
            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except jsonschema.exceptions.SchemaError as exc:
                return Check("schema_validation", "fail", f"{side} schema invalid: {exc.message}")
            schemas[side] = schema

    if not schemas:
        return Check("schema_validation", "pass", "no contract schemas to validate")

    # 2. smoke fixture inputs conform to the input schema
    rows_checked = 0
    if "input" in schemas:
        validator = jsonschema.Draft202012Validator(schemas["input"])
        for entry in node.raw.get("evals", {}).get("tier0", []):
            if entry.get("type") == "smoke" and entry.get("fixture"):
                for i, row in _iter_rows(root / entry["fixture"]):
                    if "input" not in row:
                        continue
                    errs = sorted(validator.iter_errors(row["input"]), key=lambda e: list(e.path))
                    if errs:
                        return Check(
                            "schema_validation", "fail",
                            f"{entry['fixture']} row {i}: input does not conform — {errs[0].message}",
                        )
                    rows_checked += 1

    detail = f"{len(schemas)} schema(s) valid"
    if rows_checked:
        detail += f", {rows_checked} input row(s) conform"
    return Check("schema_validation", "pass", detail)


def _check_invariants(node: Node) -> Check:
    invariants = node.raw.get("contract", {}).get("invariants", []) or []
    if not invariants:
        return Check("invariant_check", "pass", "no invariants declared")
    for expr in invariants:
        try:
            compile(expr, "<invariant>", "eval")
        except SyntaxError as exc:
            return Check("invariant_check", "fail", f"malformed invariant '{expr}': {exc.msg}")
    return Check("invariant_check", "pass", f"{len(invariants)} invariant(s) well-formed")


def _check_smoke(node: Node, root: Path, fixture: str | None) -> Check:
    if not fixture:
        return Check("smoke", "fail", "smoke check declares no fixture")
    path = root / fixture
    if not path.exists():
        return Check("smoke", "fail", f"fixture '{fixture}' not found")
    count = 0
    for i, row in _iter_rows(path):
        if row is _BAD_ROW:
            return Check("smoke", "fail", f"fixture '{fixture}' line {i} is not valid JSON")
        count += 1
    if count == 0:
        return Check("smoke", "fail", f"fixture '{fixture}' is empty")
    return Check("smoke", "pass", f"{count} fixture row(s) parse")


_BAD_ROW: Any = object()


def _iter_rows(path: Path):
    """Yield (line_no, parsed_row) for a jsonl file. Bad lines yield _BAD_ROW."""
    if not path.exists():
        return
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            yield i, json.loads(line)
        except json.JSONDecodeError:
            yield i, _BAD_ROW
