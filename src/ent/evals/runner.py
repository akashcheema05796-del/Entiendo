"""L2 — tier0 eval runner.

Runs the deterministic, sub-second checks that gate every edit (SPEC.md §5.1).
Each check type is driven by the node's `evals.tier0` manifest entries:

  - schema_validation  contract input/output $ref schemas are valid JSON Schema,
                       and every smoke fixture `input` conforms to the input schema
  - invariant_check    every `contract.invariants` expression is well-formed
  - smoke              the fixture exists and every row parses as JSON

These are static — they do not execute node code, so they stay deterministic and
fast (the whole point of tier0). Runtime invariant enforcement rides on the spans
from the instrumentation layer and lands with the health lens. tier1/tier2 are
separate, more expensive tiers (golden datasets, LLM judge) and are out of scope
here.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..manifest import Node


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
