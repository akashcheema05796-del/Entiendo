"""Partial coverage is a first-class state, and the first manifest pays rent.

Research rec E: the manifest tax is the central adoption risk (Backstage's
catalog-info.yaml is the cautionary tale). The survival kit is AI-authored
manifests + partial-coverage tolerance + immediate reciprocal value. These
tests pin the guarantees end to end:

  - ONE manifest in a many-file repo: validate, extract, eval, and `ent ci`
    all work — nothing demands all-or-nothing coverage.
  - `ent retrofit --accept` returns value ON THE SPOT: the map regenerates,
    the accepted unit's edges are reported, and its reflex eval runs — not
    a homework list.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.ci import run_ci  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.validation import validate_root  # noqa: E402


def _partial_repo(tmp_path: Path) -> Path:
    """Five source files; exactly ONE declared unit claiming one of them."""
    root = tmp_path / "app"
    (root / "core").mkdir(parents=True)
    (root / "core" / "engine.py").write_text(
        "def run(payload):\n    return {'ok': True, 'n': payload['n'] * 2}\n")
    for name in ("api.py", "db.py", "queue.py", "webhooks.py"):
        (root / "core" / name).write_text(f"# {name}: not yet declared\n")
    (root / "core" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\n"
        "kind: Node\n"
        "id: app.engine\n"
        "name: Engine\n"
        "task: Double the number.\n"
        "nodeKind: compute\n"
        "group: app\n"
        "owner: tester\n"
        "status: experimental\n"
        "claims: [core/engine.py]\n"
        "contract:\n"
        "  entrypoint: core/engine.py::run\n"
        "  invariants: [\"output['ok'] == True\"]\n"
        "  sideEffects: none\n"
        "evals:\n"
        "  tier0:\n"
        "    - type: invariant_check\n"
        "    - {type: smoke, fixture: evals/app.engine/smoke.jsonl}\n")
    (root / "evals" / "app.engine").mkdir(parents=True)
    (root / "evals" / "app.engine" / "smoke.jsonl").write_text(
        '{"name": "doubles", "input": {"n": 21}}\n')
    return root


def test_one_manifest_among_many_files_fully_works(tmp_path: Path) -> None:
    root = _partial_repo(tmp_path)
    assert validate_root(root).ok                       # one unit validates
    ext = extract(root)
    assert ext.ok, ext.errors                           # reconciles clean
    cov = ext.coverage
    assert cov["claimedCount"] == 1
    # 4 undeclared source files + the eval fixture (no unclaimed.txt yet —
    # a brand-new partial repo hasn't acknowledged anything)
    assert cov["unaccountedCount"] == 5                 # visible, not fatal
    result = run_ci(root)
    assert result.ok and result.exit_code == 0          # partial ≠ failing


def test_undeclared_files_are_named_not_hidden(tmp_path: Path) -> None:
    """Invariant 4 under partial coverage: unclaimed is VISIBLE. The map may
    be partial; it may never be silently partial."""
    ext = extract(_partial_repo(tmp_path))
    assert "core/db.py" in ext.coverage["unaccounted"]
    assert "core/webhooks.py" in ext.coverage["unaccounted"]


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ent.cli", *args],
                          cwd=str(root), capture_output=True, text=True, timeout=120)


def test_accepting_the_first_proposal_returns_value_immediately(tmp_path: Path) -> None:
    """propose → accept ONE unit → the same command prints the regenerated
    map, the unit's discovered edges, and a live eval verdict. The first
    manifest yields a graph and an eval, not a to-do list."""
    root = tmp_path / "fresh"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "maths.py").write_text("def double(x):\n    return x * 2\n")
    (root / "lib" / "extra.py").write_text("HELPER = 1\n")

    proc = _run(root, "retrofit", ".")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "fresh.lib" in proc.stdout                   # a proposal was staged

    proc = _run(root, "retrofit", ".", "--accept", "fresh.lib")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    assert "map: 1 unit(s)" in out                      # the graph, right now
    assert "`ent dev` to see it" in out
    assert "eval: fresh.lib →" in out                   # a verdict, right now
    assert (root / "entiendo" / "graph.json").exists()  # artifacts written
    # and the repo is a working partial project from this moment on
    assert validate_root(root).ok
    assert run_ci(root).exit_code == 0
