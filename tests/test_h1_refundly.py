"""Phase H1 acceptance (PLAN_v4.md) — refundly is the full 6-stage pipeline.

Six units (every relevant kind), one approval gate, one irreversible side
effect, budgets with one deliberately blown, and recorded traces that exercise
every edge — the fixture every H2–H5 acceptance runs against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.extractor import extract  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.render import build_view  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"

STAGES = {
    "refundly.parse_email": "compute",
    "refundly.orders": "state",
    "refundly.policy": "config",
    "refundly.decide": "compute",
    "refundly.gateway": "external",
    "refundly.ledger": "state",
}


def test_six_stage_pipeline_present() -> None:
    view = build_view(REFUNDLY)
    got = {n["id"]: n["nodeKind"] for n in view["nodes"]}
    assert got == STAGES


def test_reconciles_at_full_coverage() -> None:
    result = extract(REFUNDLY)
    assert result.ok, result.errors
    assert result.coverage["coverage"] == 1.0


def test_one_approval_gate_one_irreversible() -> None:
    gw = find_node(REFUNDLY, "refundly.gateway")
    assert gw.raw["approval"]["required"] is True
    assert gw.raw["contract"]["sideEffects"] == "irreversible"
    # the ledger is the written-to state
    assert find_node(REFUNDLY, "refundly.ledger").raw["contract"]["sideEffects"] == "writes"


def test_decide_and_parse_are_green() -> None:
    for uid in ("refundly.decide", "refundly.parse_email"):
        assert run_tier0(find_node(REFUNDLY, uid), REFUNDLY).verdict == "GREEN"


def test_blown_budget_is_visible_in_measured() -> None:
    gw = next(n for n in build_view(REFUNDLY)["nodes"] if n["id"] == "refundly.gateway")
    declared = gw["budgets"]["costPerCallUsd"]
    measured = gw["budgets"]["measured"]["avgCostUsd"]
    assert measured > declared              # the cost overlay has something amber to show


def test_traces_recorded_and_exercise_every_edge() -> None:
    view = build_view(REFUNDLY)
    assert len(view["traces"]) >= 3
    # every executable unit in the pipeline appears in traffic (edges exercised)
    executable = {"refundly.parse_email", "refundly.orders", "refundly.decide",
                  "refundly.gateway", "refundly.ledger"}
    assert executable.issubset(set(view["traffic"]))
    # a bad-order trace exists for the trajectory-violation demo (H4)
    bad = next(t for t in view["traces"] if t["id"] == "req-bad-order")
    order_nodes = [h["node"] for h in bad["hops"]]
    assert order_nodes.index("refundly.gateway") < order_nodes.index("refundly.orders")


def test_decide_interior_crosses_declared_edges() -> None:
    decide = find_node(REFUNDLY, "refundly.decide")
    crosses = {t["crosses"] for t in decide.raw["interior"]["tools"]}
    deps = decide.raw["dependencies"]
    declared = set(deps.get("calls", [])) | set(deps.get("writes", [])) | set(deps.get("config", []))
    assert crosses.issubset(declared)       # reconciler-clean
