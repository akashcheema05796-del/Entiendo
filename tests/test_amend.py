"""`ent amend` — sideEffects contradictions become acceptable amendments.

astrobee gap 5: ~20 extractor notes said "this unit uses subprocess while
declaring sideEffects: none" and then scrolled away — no workflow resolved
them. Now each contradiction is a staged amendment, listed with evidence and
accepted one unit at a time; the human blesses the contract change, the tool
does only the mechanical edit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent.commands.amend import apply_amendment, find_amendments  # noqa: E402


def _repo(tmp_path: Path, body: str, side_effects: str = "none") -> Path:
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "tool.py").write_text(body)
    manifest = {
        "apiVersion": "entiendo/v1", "kind": "Node", "id": "proj.app",
        "name": "app", "task": "a unit for the amend tests",
        "nodeKind": "compute", "group": "proj", "owner": "tests",
        "status": "experimental", "claims": ["app/tool.py"],
        "contract": {"invariants": [], "sideEffects": side_effects},
        "dependencies": {"calls": [], "reads": [], "writes": [], "config": []},
        "evals": {"tier0": [{"type": "invariant_check"}]},
        "observability": {"spanName": "proj.app"},
        "approval": {"required": False},
    }
    (root / "app" / "entiendo.node.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    return root


def test_subprocess_under_none_is_a_staged_amendment(tmp_path: Path) -> None:
    root = _repo(tmp_path, "import subprocess\n\ndef run(c):\n    return subprocess.run(c)\n")
    staged = find_amendments(root)
    assert len(staged) == 1
    a = staged[0]
    assert a["node"] == "proj.app"
    assert a["proposed"] == "external"
    assert any(ev["pattern"] == "subprocess" for ev in a["evidence"])


def test_visibility_notes_are_not_effect_amendments(tmp_path: Path) -> None:
    """importlib / getattr dispatch are dependency-visibility notes, not
    effects — they must never propose a sideEffects change."""
    root = _repo(tmp_path, "import importlib\n\ndef load(n):\n    return importlib.import_module(n)\n")
    assert find_amendments(root) == []


def test_already_honest_units_stage_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path, "import subprocess\n\ndef run(c):\n    return subprocess.run(c)\n",
                 side_effects="external")
    assert find_amendments(root) == []


def test_accept_flips_the_declaration_in_place(tmp_path: Path) -> None:
    root = _repo(tmp_path, "import requests\n\ndef get(u):\n    return requests.get(u)\n")
    path = apply_amendment(root, "proj.app")
    assert path is not None
    manifest = yaml.safe_load(path.read_text())
    assert manifest["contract"]["sideEffects"] == "external"
    assert find_amendments(root) == []          # resolved — nothing staged


def test_accept_of_unknown_unit_is_a_noop(tmp_path: Path) -> None:
    root = _repo(tmp_path, "def pure(x):\n    return x\n")
    assert apply_amendment(root, "proj.app") is None
    assert apply_amendment(root, "nonexistent") is None


def test_cli_lists_and_accepts(tmp_path: Path) -> None:
    import subprocess
    import sys
    root = _repo(tmp_path, "import subprocess\n\ndef run(c):\n    return subprocess.run(c)\n")

    proc = subprocess.run([sys.executable, "-m", "ent.cli", "amend", "."],
                          cwd=str(root), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0
    assert "proj.app: sideEffects none → external" in proc.stdout
    assert "subprocess" in proc.stdout
    assert "one at a time" in proc.stdout

    proc = subprocess.run([sys.executable, "-m", "ent.cli", "amend", ".",
                           "--accept", "proj.app"],
                          cwd=str(root), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = yaml.safe_load((root / "app" / "entiendo.node.yaml").read_text())
    assert manifest["contract"]["sideEffects"] == "external"
