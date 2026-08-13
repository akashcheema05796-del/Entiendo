"""Coverage must tell both truths (astrobee gap 4).

astrobee reported "coverage 7%" and "100% of recognized files" — both
accurate, together sounding like a contradiction, because 2,500 of its 2,695
files (C++ core, ROS artifacts) have no adapter at all. coverage.json now
separates the universes: adapter-recognized files vs files beyond every
adapter, counted by extension, and the headline states both numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent.extractor import coverage_headline, extract  # noqa: E402


def _astrobee_shaped(tmp_path: Path) -> Path:
    """2 .py (1 claimed), 3 .cc, 1 .h — a miniature of the astrobee split."""
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app" / "claimed.py").write_text("def go(x):\n    return x\n")
    (root / "loose.py").write_text("X = 1\n")
    for name in ("a.cc", "b.cc", "c.cc"):
        (root / name).write_text("// flight software\n")
    (root / "core.h").write_text("// header\n")
    manifest = {
        "apiVersion": "entiendo/v1", "kind": "Node", "id": "repo.app",
        "name": "app", "task": "claimed unit for the coverage tests",
        "nodeKind": "compute", "group": "repo", "owner": "tests",
        "status": "experimental", "claims": ["app/claimed.py"],
        "contract": {"invariants": [], "sideEffects": "none"},
        "dependencies": {"calls": [], "reads": [], "writes": [], "config": []},
        "evals": {"tier0": [{"type": "invariant_check"}]},
        "observability": {"spanName": "repo.app"},
        "approval": {"required": False},
    }
    (root / "app" / "entiendo.node.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    return root


def test_recognized_universe_is_separated(tmp_path: Path) -> None:
    cov = extract(_astrobee_shaped(tmp_path)).coverage
    rec = cov["recognized"]
    assert rec["total"] == 2                     # only the .py files
    assert rec["accounted"] == 1
    assert rec["coverage"] == 0.5
    assert ".py" in rec["note"]


def test_unmapped_files_are_counted_by_extension(tmp_path: Path) -> None:
    cov = extract(_astrobee_shaped(tmp_path)).coverage
    assert cov["unmappedByExtension"][".cc"] == 3
    assert cov["unmappedByExtension"][".h"] == 1
    # sorted most-numerous first — the operator reads the biggest hole first
    assert list(cov["unmappedByExtension"])[0] == ".cc"


def test_headline_states_both_truths(tmp_path: Path) -> None:
    cov = extract(_astrobee_shaped(tmp_path)).coverage
    line = coverage_headline(cov)
    assert "adapter-recognized" in line
    assert "beyond every adapter" in line
    assert ".cc 3" in line


def test_headline_on_a_fully_recognized_repo_stays_clean(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app" / "claimed.py").write_text("def go(x):\n    return x\n")
    manifest = {
        "apiVersion": "entiendo/v1", "kind": "Node", "id": "repo.app",
        "name": "app", "task": "claimed unit", "nodeKind": "compute",
        "group": "repo", "owner": "tests", "status": "experimental",
        "claims": ["app/claimed.py"],
        "contract": {"invariants": [], "sideEffects": "none"},
        "dependencies": {"calls": [], "reads": [], "writes": [], "config": []},
        "evals": {"tier0": [{"type": "invariant_check"}]},
        "observability": {"spanName": "repo.app"},
        "approval": {"required": False},
    }
    (root / "app" / "entiendo.node.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    line = coverage_headline(extract(root).coverage)
    assert "beyond every adapter" not in line


def test_artifact_carries_the_split(tmp_path: Path) -> None:
    from ent.extractor import write_artifacts
    root = _astrobee_shaped(tmp_path)
    write_artifacts(extract(root), root)
    cov = json.loads((root / "entiendo" / "coverage.json").read_text())
    assert cov["recognized"]["total"] == 2
    assert cov["unmappedByExtension"] == {".cc": 3, ".h": 1}
