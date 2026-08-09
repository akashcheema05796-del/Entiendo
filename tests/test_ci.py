"""`ent ci` — the one CI/pre-commit gate (gap analysis §4).

run_ci collapses validate + reconcile + eval into a single pass/fail. The example
projects pass; a drifted project fails (and passes under --soft); an invalid
manifest fails the validate stage.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.ci import run_ci  # noqa: E402
from ent.commands import ci as ci_cmd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"
REFUNDLY = REPO_ROOT / "examples" / "refundly"


def _stages(result) -> dict[str, object]:
    return {s.name: s for s in result.stages}


def _mkproject(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _node(node_id: str, *, claims: list[str], calls: list[str] | None = None) -> str:
    calls_yaml = "[" + ", ".join(calls or []) + "]"
    claims_yaml = "\n".join(f"  - {c}" for c in claims)
    return f"""\
apiVersion: entiendo/v1
kind: Node
id: {node_id}
name: {node_id}
nodeKind: compute
owner: me
claims:
{claims_yaml}
contract:
  sideEffects: none
dependencies:
  calls: {calls_yaml}
"""


def test_greenfield_passes_all_stages() -> None:
    result = run_ci(GREENFIELD)
    assert result.ok and result.exit_code == 0
    stages = _stages(result)
    assert {"validate", "reconcile", "eval", "tier1", "budgets"} == set(stages)
    assert all(s.ok for s in result.stages)
    # greenfield's golden is unblessed → advisory, never gating (v6 3.2)
    assert "advisory" in stages["tier1"].detail


def test_refundly_detects_its_seeded_budget_overage() -> None:
    """refundly deliberately ships gateway 0.05 $/call against a declared 0.01
    budget (the cost-overlay showcase). Now that budgets GATE (research rec C),
    the example doubles as the proof: every other stage passes, the budget
    stage names the overage, and the exit is the documented DEGRADED 4."""
    result = run_ci(REFUNDLY)
    stages = _stages(result)
    for name in ("validate", "reconcile", "eval", "tier1"):
        assert stages[name].ok, (name, stages[name].detail)
    budget = stages["budgets"]
    assert not budget.ok
    assert any("refundly.gateway" in w and "$/call" in w for w in budget.warnings)
    assert budget.exit_severity == 4 and result.exit_code == 4


def test_drift_fails_ci(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/one.py": "from b.two import thing\n",
        "b/two.py": "thing = 1\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"]),   # undeclared → drift
        "b/entiendo.node.yaml": _node("b.two", claims=["b/two.py"]),
    })
    result = run_ci(root)
    assert not result.ok
    assert _stages(result)["reconcile"].ok is False


def test_soft_lets_drift_pass_ci(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/one.py": "from b.two import thing\n",
        "b/two.py": "thing = 1\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/one.py"]),
        "b/entiendo.node.yaml": _node("b.two", claims=["b/two.py"]),
    })
    result = run_ci(root, soft=True)
    reconcile = _stages(result)["reconcile"]
    assert reconcile.ok and reconcile.warnings          # drift downgraded to a warning
    assert result.ok


def test_invalid_manifest_fails_validate_stage(tmp_path: Path) -> None:
    # dependencies.calls: null is a schema violation
    _mkproject(tmp_path, {
        "a/one.py": "x = 1\n",
        "a/entiendo.node.yaml": "apiVersion: entiendo/v1\nkind: Node\nid: a.one\n"
                                "name: a.one\nnodeKind: compute\nowner: me\n"
                                "claims:\n  - a/one.py\ncontract:\n  sideEffects: none\n"
                                "dependencies:\n  calls:\n",
    })
    result = run_ci(tmp_path)
    assert not result.ok
    assert _stages(result)["validate"].ok is False


def test_cli_exit_codes(capsys) -> None:
    assert ci_cmd._run(argparse.Namespace(root=str(GREENFIELD), soft=False)) == 0
    out = capsys.readouterr().out
    assert "entiendo ci" in out and "ent ci passed" in out
