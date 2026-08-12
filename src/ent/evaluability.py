"""Evaluability grading — three states instead of one smear of UNTESTED red.

The law says a boundary is a unit iff it can be evaluated independently on
given data. Today the map answers that with one colour: a unit without
verdicts is "untested", whether it is one golden row away from trustworthy
or shaped wrong for trust entirely. This module splits that smear:

  ready       takes values, no effects beyond its declarations, statically
              clock-clean → the only thing missing is ground truth. A data
              chore, not a design problem ("awaiting goldens" / "awaiting
              blessing").
  evaluable-after-refactor
              contracted, but I/O is fused with the logic (reads the clock,
              talks to the world without a declared edge to stub) → the law
              fires NOW, at build time, telling the Builder to split it
              before the code hardens.
  interior    documented but never contracted — no entrypoint, no harness;
              not independently judgeable by construction.

Honesty constraint (the capability-manifest rule applied to ourselves): the
probe only observes the paths it executes, so "ready" is graded EVIDENCE,
never proof — the label is always `ready (probed)` or `ready (static)`,
never "verified". A unit that is pure on dummy inputs can still open a
socket on real ones; the grade upgrades as real fixtures arrive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

READY = "ready"
AFTER_REFACTOR = "evaluable-after-refactor"
INTERIOR = "interior"


def _has_smoke_fixture(node: Any, root: Path) -> bool:
    for entry in (node.raw.get("evals", {}) or {}).get("tier0", []) or []:
        fixture = entry.get("fixture") if isinstance(entry, dict) else None
        if fixture and (Path(root) / fixture).exists():
            return True
    return False


def _golden_state(node: Any, root: Path) -> str | None:
    """None = blessed and gating · 'blessing' = golden exists, unsigned ·
    'goldens' = no golden dataset at all."""
    golden = next((e for e in (node.raw.get("evals", {}) or {}).get("tier1", []) or []
                   if isinstance(e, dict) and e.get("type") == "golden"
                   and e.get("dataset")), None)
    if golden is None or not (Path(root) / golden["dataset"]).exists():
        return "goldens"
    from .baselines import blessing_valid
    if golden.get("humanBlessed") is True and \
            blessing_valid(root, node.id, Path(root) / golden["dataset"]):
        return None
    return "blessing"


def grade(node: Any, root: Path, clock_findings: list[str] | None = None) -> dict[str, Any]:
    """One unit's evaluability: {grade, evidence, label, why?, awaiting?}."""
    root = Path(root)
    contract = node.raw.get("contract", {}) or {}
    if not (contract.get("entrypoint") or contract.get("harness")):
        return {
            "grade": INTERIOR,
            "evidence": "static",
            "label": "interior — documented, never contracted",
            "why": ["no contract.entrypoint or harness: not independently "
                    "judgeable; give it one (or fold it into the unit that is)"],
        }

    why: list[str] = []
    for finding in clock_findings or []:
        why.append(f"reads the clock: {finding} — output depends on WHEN it "
                   "runs; inject the time as an input")
    side = contract.get("sideEffects", "none")
    deps = node.raw.get("dependencies", {}) or {}
    if node.raw.get("nodeKind") == "compute":
        if side in ("external", "irreversible"):
            why.append(f"sideEffects: {side} fused into a compute unit — put "
                       "the effectful call behind a declared dependency so the "
                       "logic is judgeable on data alone (stubs do the rest)")
        elif side == "writes" and not (deps.get("writes") or []):
            why.append("sideEffects: writes with no declared writes edge — the "
                       "write is fused into the logic instead of stubbed "
                       "behind a dependency")

    if why:
        return {
            "grade": AFTER_REFACTOR,
            "evidence": "static",
            "label": "evaluable after a refactor — the law fires now, before "
                     "the code hardens",
            "why": why,
        }

    evidence = "probed" if _has_smoke_fixture(node, root) else "static"
    awaiting = _golden_state(node, root)
    label = f"ready ({evidence})"
    if awaiting:
        label += f" — awaiting {awaiting}"
    return {
        "grade": READY,
        "evidence": evidence,
        "label": label,
        **({"awaiting": awaiting} if awaiting else {}),
    }


def grade_all(root: Path, nodes: list[Any]) -> dict[str, dict[str, Any]]:
    """Every unit's grade, with the clock detector's static findings wired in
    (the transitive call graph needs all units at once)."""
    from .detectors import time_static
    clock = time_static.analyze_units(root, nodes)
    return {
        n.id: grade(n, root, clock.get(n.id, {}).get("findings") or [])
        for n in nodes
    }
