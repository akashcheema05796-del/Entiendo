"""`ent ci --enqueue-failures` — red verdicts become builder tasks (gap 6).

The judge must never be the builder (propose-verify is access control), but
nothing stops it from EMITTING the work item: report lines cannot be
delegated, structures can. Each RED/ERROR unit becomes one steering request
the operator loop consumes through the normal Bridge, with mechanical
remediation options ranked — and an explicit prohibition on golden
authorship, because the builder must not write the answers it is graded
against.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent import steering  # noqa: E402

_MISSING = "module_that_does_not_exist_anywhere_xyz"


def _repo(tmp_path: Path, body: str, *, extra_claim: str | None = None) -> Path:
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "mod.py").write_text(body)
    claims = ["app/mod.py"]
    if extra_claim:
        (root / "app" / extra_claim).write_text("def clean(x):\n    return x\n")
        claims.append(f"app/{extra_claim}")
    manifest = {
        "apiVersion": "entiendo/v1", "kind": "Node", "id": "proj.app",
        "name": "app", "task": "a unit for the steering-bridge tests",
        "nodeKind": "compute", "group": "proj", "owner": "tests",
        "status": "experimental", "claims": claims,
        "contract": {"entrypoint": "app/mod.py::go", "invariants": [],
                     "sideEffects": "none"},
        "dependencies": {"calls": [], "reads": [], "writes": [], "config": []},
        "evals": {"tier0": [{"type": "invariant_check"},
                            {"type": "smoke", "fixture": "evals/smoke.jsonl"}]},
        "observability": {"spanName": "proj.app"},
        "approval": {"required": False},
    }
    (root / "evals").mkdir()
    (root / "evals" / "smoke.jsonl").write_text(json.dumps({"input": 1, "expect": 1}) + "\n")
    (root / "app" / "entiendo.node.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    return root


def _ci(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ent.cli", "ci", *flags],
                          cwd=str(root), capture_output=True, text=True, timeout=300)


def test_error_unit_becomes_one_steering_task(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"import {_MISSING}\n\ndef go(x):\n    return x\n")
    proc = _ci(root, "--enqueue-failures")
    assert proc.returncode == 2                      # the gate still fails
    assert "queued for the builder" in proc.stdout
    tasks = steering.pending(root)
    assert len(tasks) == 1
    assert tasks[0]["unit"] == "proj.app"


def test_task_carries_diagnosis_requires_hint_and_probed_candidate(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"import {_MISSING}\n\ndef go(x):\n    return x\n",
                 extra_claim="pure.py")
    _ci(root, "--enqueue-failures")
    instruction = steering.pending(root)[0]["instruction"]
    assert f"No module named '{_MISSING}'" in instruction
    assert f"contract.requires: [{_MISSING}]" in instruction
    assert "app/pure.py::clean" in instruction       # probed importable candidate
    assert "ENV-BLOCKED" in instruction


def test_golden_authorship_is_explicitly_forbidden_in_every_task(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"import {_MISSING}\n\ndef go(x):\n    return x\n")
    _ci(root, "--enqueue-failures")
    instruction = steering.pending(root)[0]["instruction"]
    assert "Do NOT author or bless golden datasets" in instruction


def test_enqueue_is_idempotent_across_runs(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"import {_MISSING}\n\ndef go(x):\n    return x\n")
    _ci(root, "--enqueue-failures")
    _ci(root, "--enqueue-failures")
    assert len(steering.pending(root)) == 1          # one live task per unit


def test_resolved_unit_can_be_requeued_after_verdict(tmp_path: Path) -> None:
    """Once the operator posts a verdict the task is consumed; a STILL-red
    re-run may queue a fresh one — nothing is forgotten, nothing duplicates."""
    root = _repo(tmp_path, f"import {_MISSING}\n\ndef go(x):\n    return x\n")
    _ci(root, "--enqueue-failures")
    task = steering.claim_next(root)
    steering.post_verdict(root, task["id"], {"verdict": "ERROR", "note": "still broken"})
    assert steering.pending(root) == []
    _ci(root, "--enqueue-failures")
    assert len(steering.pending(root)) == 1


def test_green_gate_enqueues_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path, "def go(x):\n    return x\n")
    proc = _ci(root, "--enqueue-failures")
    assert proc.returncode == 0
    assert steering.pending(root) == []
    assert "queued for the builder" not in proc.stdout


def test_without_the_flag_nothing_is_queued(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"import {_MISSING}\n\ndef go(x):\n    return x\n")
    _ci(root)
    assert steering.pending(root) == []
