"""Coverage-ramp target — `--min-coverage` on `ent extract` and `ent ci` (§3/§7).

A migrating team ratchets coverage up by setting a threshold in CI: the build
fails while claimed+acknowledged coverage is below it, and passes once they've
claimed (or acknowledged) enough. Clean projects at 100% pass any threshold.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.ci import run_ci  # noqa: E402
from ent.commands import extract as extract_cmd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _low_coverage_project(tmp_path: Path) -> Path:
    # one claimed file + one unaccounted file → coverage 50%
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.py").write_text("x = 1\n")
    (tmp_path / "loose.py").write_text("y = 2\n")               # unclaimed, unacknowledged
    (tmp_path / "a" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: a.one\nname: a.one\n"
        "nodeKind: compute\nowner: me\nclaims:\n  - a/one.py\n"
        "contract:\n  sideEffects: none\n")
    return tmp_path


def _extract(root: Path, *, min_coverage=None) -> int:
    return extract_cmd._run(argparse.Namespace(
        root=str(root), check=True, soft=False, min_coverage=min_coverage))


# --------------------------------------------------------------------------- #
# ent extract --min-coverage
# --------------------------------------------------------------------------- #

def test_extract_passes_when_above_threshold() -> None:
    assert _extract(GREENFIELD, min_coverage=90) == 0        # greenfield is 100%


def test_extract_fails_below_threshold(tmp_path: Path, capsys) -> None:
    root = _low_coverage_project(tmp_path)
    assert _extract(root, min_coverage=80) == 1              # 50% < 80%
    assert "below the --min-coverage" in capsys.readouterr().out


def test_extract_passes_when_threshold_met(tmp_path: Path) -> None:
    root = _low_coverage_project(tmp_path)
    assert _extract(root, min_coverage=40) == 0              # 50% >= 40%


def test_extract_without_flag_is_unchanged(tmp_path: Path) -> None:
    root = _low_coverage_project(tmp_path)
    assert _extract(root, min_coverage=None) == 0            # unaccounted alone never fails


# --------------------------------------------------------------------------- #
# ent ci --min-coverage adds a coverage stage
# --------------------------------------------------------------------------- #

def test_ci_coverage_stage_only_when_requested() -> None:
    names = {s.name for s in run_ci(GREENFIELD).stages}
    assert "coverage" not in names                           # off by default
    names = {s.name for s in run_ci(GREENFIELD, min_coverage=90).stages}
    assert "coverage" in names


def test_ci_fails_when_coverage_below_target(tmp_path: Path) -> None:
    root = _low_coverage_project(tmp_path)
    result = run_ci(root, min_coverage=80)
    cov = next(s for s in result.stages if s.name == "coverage")
    assert cov.ok is False and not result.ok


def test_ci_passes_coverage_on_greenfield() -> None:
    result = run_ci(GREENFIELD, min_coverage=100)
    assert result.ok
    assert next(s for s in result.stages if s.name == "coverage").ok
