"""ENV-BLOCKED — "wrong environment" must stop masquerading as "broken code".

astrobee gap 2: five units' entrypoints import ROS packages that can never
resolve outside a ROS install, and the eval reported ERROR — the same verdict
a genuinely broken unit gets, and it reddened the gate. `contract.requires`
declares the runtimes a unit needs; a missing one now yields ENV-BLOCKED:
exit 0, counted separately, grey on the map, and explicitly labelled.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent import verdicts  # noqa: E402
from ent.ci import run_ci  # noqa: E402
from ent.evals.runner import run_tier0, run_tier1  # noqa: E402
from ent.manifest import Node  # noqa: E402
from ent.validation import validate_root  # noqa: E402

_MISSING = "module_that_does_not_exist_anywhere_xyz"


def _write_unit(root: Path, *, requires: list[str] | None = None,
                body: str = "def go(x):\n    return x\n") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.py").write_text(body)
    (root / "evals").mkdir(exist_ok=True)
    (root / "evals" / "smoke.jsonl").write_text(json.dumps({"input": 1, "expect": 1}) + "\n")
    contract: dict = {"entrypoint": "mod.py::go", "invariants": [], "sideEffects": "none"}
    if requires is not None:
        contract["requires"] = requires
    manifest = {
        "apiVersion": "entiendo/v1", "kind": "Node", "id": "proj.unit",
        "name": "unit", "task": "a unit for the env-blocked tests",
        "nodeKind": "compute", "group": "proj", "owner": "tests",
        "status": "experimental", "claims": ["mod.py"],
        "contract": contract,
        "dependencies": {"calls": [], "reads": [], "writes": [], "config": []},
        "evals": {"tier0": [{"type": "invariant_check"},
                            {"type": "smoke", "fixture": "evals/smoke.jsonl"}]},
        "observability": {"spanName": "proj.unit"},
        "approval": {"required": False},
    }
    path = root / "entiendo.node.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return path


def _node(path: Path) -> Node:
    return Node.from_manifest(yaml.safe_load(path.read_text()), path)


def test_missing_requirement_is_env_blocked_not_error(tmp_path: Path) -> None:
    path = _write_unit(tmp_path / "proj", requires=[_MISSING])
    res = run_tier0(_node(path), tmp_path / "proj")
    assert res.verdict == verdicts.ENV_BLOCKED
    detail = res.checks[0].detail
    assert _MISSING in detail and "not broken" in detail


def test_satisfied_requirements_proceed_to_green(tmp_path: Path) -> None:
    path = _write_unit(tmp_path / "proj", requires=["json", "os"])
    res = run_tier0(_node(path), tmp_path / "proj")
    assert res.verdict == verdicts.GREEN


def test_undeclared_missing_import_is_still_error(tmp_path: Path) -> None:
    """The honest ERROR survives: a unit that fails to import WITHOUT
    declaring the runtime keeps reading ERROR — the conflation is only
    resolved by declaring, never silently."""
    path = _write_unit(tmp_path / "proj",
                       body=f"import {_MISSING}\n\ndef go(x):\n    return x\n")
    res = run_tier0(_node(path), tmp_path / "proj")
    assert res.verdict == verdicts.ERROR


def test_env_blocked_does_not_redden_ci_and_is_labelled(tmp_path: Path) -> None:
    _write_unit(tmp_path / "proj", requires=[_MISSING])
    result = run_ci(tmp_path / "proj")
    assert result.exit_code == 0
    eval_stage = next(s for s in result.stages if s.name == "eval")
    assert "1 env-blocked" in eval_stage.detail
    assert "not failures" in eval_stage.detail


def test_requires_validates_against_the_schema(tmp_path: Path) -> None:
    _write_unit(tmp_path / "proj", requires=["rosbag", "tf"])
    report = validate_root(tmp_path / "proj")
    assert report.ok, [e for f in report.files for e in f.errors]


def test_tier1_is_env_blocked_too(tmp_path: Path) -> None:
    path = _write_unit(tmp_path / "proj", requires=[_MISSING])
    manifest = yaml.safe_load(path.read_text())
    (tmp_path / "proj" / "evals" / "rows.jsonl").write_text(
        json.dumps({"input": 1, "expect": 1}) + "\n")
    manifest["evals"]["tier1"] = [{"type": "golden", "dataset": "evals/rows.jsonl",
                                   "metric": "exact_match"}]
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    res = run_tier1(_node(path), tmp_path / "proj")
    assert res.verdict == verdicts.ENV_BLOCKED


def test_env_blocked_renders_grey_and_exits_zero() -> None:
    assert verdicts.colour(verdicts.ENV_BLOCKED) == "grey"
    assert verdicts.exit_code(verdicts.ENV_BLOCKED) == 0
