"""`ent doctor` — self-diagnosis (gap analysis §4/§6, first-run).

`diagnose()` is pure, so it's checked without a subprocess: the environment
checks (python/deps/schema/languages), the model-key presence report (by name,
never value — Invariant 6), and the project checks (reconciles vs drift).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.commands import doctor  # noqa: E402
from ent.commands.doctor import FAIL, OK, WARN, diagnose, worst_level  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _by_name(checks) -> dict[str, object]:
    return {c.name: c for c in checks}


def test_core_environment_is_healthy() -> None:
    checks = _by_name(diagnose(GREENFIELD))
    assert checks["python"].level == OK
    assert checks["dep:pyyaml"].level == OK
    assert checks["dep:jsonschema"].level == OK
    assert checks["schema"].level == OK


def test_languages_check_reports_python_and_typescript() -> None:
    # ties the seam (PR #34) into the doctor: both extractors registered
    check = _by_name(diagnose(GREENFIELD))["languages"]
    assert check.level == OK
    assert "python" in check.detail and "typescript" in check.detail


def test_model_key_absent_is_a_warning_not_a_failure(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    check = _by_name(diagnose(GREENFIELD))["model-key"]
    assert check.level == WARN
    assert "not set" in check.detail


def test_model_key_value_is_never_rendered(monkeypatch) -> None:
    # Invariant 6: presence only — the secret value must never appear in output.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret-value")
    check = _by_name(diagnose(GREENFIELD))["model-key"]
    assert check.level == OK
    assert "sk-super-secret-value" not in check.detail


def test_greenfield_project_reconciles() -> None:
    checks = _by_name(diagnose(GREENFIELD))
    assert checks["project"].level == OK
    assert checks["validate"].level == OK
    assert checks["reconcile"].level == OK
    assert "coverage" in checks["reconcile"].detail


def test_empty_dir_is_not_a_failure(tmp_path: Path) -> None:
    checks = _by_name(diagnose(tmp_path))
    assert "validate" not in checks and "reconcile" not in checks   # no project checks
    assert checks["project"].level == OK
    assert worst_level(diagnose(tmp_path)) in (OK, WARN)            # never FAIL on a clean env


def test_drifted_project_is_a_failure(tmp_path: Path) -> None:
    # a unit that imports a neighbour it doesn't declare → reconcile FAIL
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "one.py").write_text("from b.two import thing\n")
    (tmp_path / "b" / "two.py").write_text("thing = 1\n")
    manifest = """\
apiVersion: entiendo/v1
kind: Node
id: {id}
name: {id}
nodeKind: compute
owner: me
claims:
  - {claim}
contract:
  sideEffects: none
"""
    (tmp_path / "a" / "entiendo.node.yaml").write_text(manifest.format(id="a.one", claim="a/one.py"))
    (tmp_path / "b" / "entiendo.node.yaml").write_text(manifest.format(id="b.two", claim="b/two.py"))
    checks = _by_name(diagnose(tmp_path))
    assert checks["reconcile"].level == FAIL
    assert worst_level(diagnose(tmp_path)) == FAIL


def test_run_exit_code_zero_on_healthy_project(capsys) -> None:
    import argparse
    code = doctor._run(argparse.Namespace(root=str(GREENFIELD)))
    out = capsys.readouterr().out
    assert code == 0
    assert "entiendo doctor" in out and "✓" in out
