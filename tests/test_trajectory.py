"""Phase D acceptance (PLAN_v3.md §D) — trajectory invariants + tool registry.

- a fixture where the right answer is produced via a FORBIDDEN order → reflex RED;
- an undeclared border-crossing tool → `ent extract --check` fails naming unit + tool;
- `ent.guard` raises on an out-of-registry call;
- the refundly example demonstrates both and evals GREEN.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import ent  # noqa: E402
from ent import trajectory  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"

REGISTRY = {"order_lookup", "issue_refund"}


# --------------------------------------------------------------------------- #
# the pure evaluator
# --------------------------------------------------------------------------- #

def test_good_order_passes() -> None:
    rule = {"order": ["order_lookup before issue_refund"], "maxSteps": 8, "registryOnly": True}
    ok, _ = trajectory.evaluate(rule, ["order_lookup", "issue_refund"], REGISTRY)
    assert ok


def test_forbidden_order_fails() -> None:
    rule = {"order": ["order_lookup before issue_refund"]}
    ok, detail = trajectory.evaluate(rule, ["issue_refund", "order_lookup"], REGISTRY)
    assert not ok and "must precede" in detail


def test_underscore_before_form_parses() -> None:
    rule = {"order": ["order_lookup_before_issue_refund"]}
    ok, _ = trajectory.evaluate(rule, ["order_lookup", "issue_refund"], REGISTRY)
    assert ok
    bad, _ = trajectory.evaluate(rule, ["issue_refund", "order_lookup"], REGISTRY)
    assert not bad


def test_registry_only_rejects_outsider() -> None:
    rule = {"registryOnly": True}
    ok, detail = trajectory.evaluate(rule, ["order_lookup", "delete_everything"], REGISTRY)
    assert not ok and "delete_everything" in detail


def test_max_steps_bound() -> None:
    rule = {"maxSteps": 2}
    ok, detail = trajectory.evaluate(rule, ["a", "b", "c"], set())
    assert not ok and "maxSteps" in detail


def test_b_without_required_a_fails() -> None:
    rule = {"order": ["order_lookup before issue_refund"]}
    ok, detail = trajectory.evaluate(rule, ["issue_refund"], REGISTRY)
    assert not ok and "without the required preceding" in detail


# --------------------------------------------------------------------------- #
# the reflex tier0 verdict, over a run-log fixture
# --------------------------------------------------------------------------- #

def _agentic_node(tmp_path: Path, traj_rows: list[str]) -> Path:
    """A minimal agentic unit whose only tier0 signal is a trajectory fixture."""
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('agent.thing')\ndef run(req):\n    return {'ok': True}\n")
    (tmp_path / "evals" / "agent.thing").mkdir(parents=True)
    (tmp_path / "evals" / "agent.thing" / "traj.jsonl").write_text(
        "".join('{"tool": "%s"}\n' % t for t in traj_rows))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: agent.thing\nname: Agent\nnodeKind: compute\n"
        "owner: me\nclaims: [mod.py]\n"
        "contract: {invariants: [], sideEffects: none}\n"
        "interior:\n  tools:\n    - {name: order_lookup, crosses: agent.orders}\n"
        "    - {name: issue_refund, crosses: agent.orders}\n  maxSteps: 8\n"
        "evals:\n  tier0:\n    - type: trajectory\n      fixture: evals/agent.thing/traj.jsonl\n"
        "      order: [\"order_lookup before issue_refund\"]\n      registryOnly: true\n")
    return tmp_path


def test_reflex_green_on_good_trajectory(tmp_path: Path) -> None:
    root = _agentic_node(tmp_path, ["order_lookup", "issue_refund"])
    result = run_tier0(find_node(root, "agent.thing"), root)
    assert result.verdict == "GREEN"


def test_reflex_red_on_forbidden_order(tmp_path: Path) -> None:
    """The right answer via the wrong order is RED (PLAN_v3 §D acceptance)."""
    root = _agentic_node(tmp_path, ["issue_refund", "order_lookup"])
    result = run_tier0(find_node(root, "agent.thing"), root)
    assert result.verdict == "RED"
    assert any(c.type == "trajectory" and c.status == "fail" for c in result.checks)


# --------------------------------------------------------------------------- #
# the reconciler: an undeclared border-crossing tool is drift
# --------------------------------------------------------------------------- #

def _two_units(tmp_path: Path, *, declare_edge: bool) -> Path:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 1\n")
    (tmp_path / "ua").mkdir(); (tmp_path / "ub").mkdir()
    deps = "dependencies:\n  calls: [demo.b]\n" if declare_edge else ""
    (tmp_path / "ua" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.a\nname: A\nnodeKind: compute\n"
        "owner: me\nclaims: [a.py]\ncontract: {invariants: [], sideEffects: none}\n"
        + deps +
        "interior:\n  tools:\n    - {name: call_b, crosses: demo.b}\n  maxSteps: 4\n"
        "evals: {tier0: [{type: invariant_check}]}\n")
    (tmp_path / "ub" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.b\nname: B\nnodeKind: compute\n"
        "owner: me\nclaims: [b.py]\ncontract: {invariants: [], sideEffects: none}\n"
        "evals: {tier0: [{type: invariant_check}]}\n")
    return tmp_path


def test_declared_crossing_reconciles(tmp_path: Path) -> None:
    result = extract(_two_units(tmp_path, declare_edge=True))
    assert result.ok, result.errors


def test_undeclared_crossing_tool_is_drift(tmp_path: Path) -> None:
    result = extract(_two_units(tmp_path, declare_edge=False))
    assert not result.ok
    blob = "\n".join(result.errors)
    assert "demo.a" in blob and "call_b" in blob        # names the unit AND the tool
    assert "demo.b" in blob


# --------------------------------------------------------------------------- #
# the runtime guard
# --------------------------------------------------------------------------- #

def test_guard_allows_registry_and_records() -> None:
    log: list = []
    gate = ent.guard(["order_lookup", "issue_refund"], record_calls=log)
    gate("order_lookup"); gate("issue_refund")
    assert log == ["order_lookup", "issue_refund"]


def test_guard_raises_outside_registry() -> None:
    gate = ent.guard(["order_lookup"])
    with pytest.raises(ent.instrument.RegistryViolation):
        gate("issue_refund")


# --------------------------------------------------------------------------- #
# the reference example, end to end
# --------------------------------------------------------------------------- #

def test_refundly_reconciles_and_decide_is_green() -> None:
    result = extract(REFUNDLY)
    assert result.ok, result.errors
    decide = find_node(REFUNDLY, "refundly.decide")
    assert run_tier0(decide, REFUNDLY).verdict == "GREEN"
