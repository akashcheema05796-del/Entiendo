"""The astrobee showcase example stays honest — and green.

examples/astrobee is a vendored slice of NASA's astrobee repo (the
real-world retrofit, akashdatageek/astrobee PRs #3-#4), chosen so every
honest state shows up on real code: GREEN on authored fixtures, ENV-BLOCKED
for the ROS-bound unit, one package-map edge, and a pinned latent bug. These
tests keep the showcase telling the truth.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import verdicts  # noqa: E402
from ent.ci import run_ci  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.manifest import find_node  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "examples" / "astrobee"


def test_the_showcase_gate_is_green() -> None:
    result = run_ci(ROOT)
    assert result.exit_code == 0, [s.detail for s in result.stages if not s.ok]
    eval_stage = next(s for s in result.stages if s.name == "eval")
    assert "5 green" in eval_stage.detail
    assert "1 env-blocked" in eval_stage.detail


def test_the_package_map_edge_is_verified() -> None:
    """merge imports localization_common by installed name from a catkin-style
    layout — the edge only exists because of the repo-wide package map."""
    ext = extract(ROOT)
    assert ext.ok, ext.errors
    edges = {(e["from"], e["to"]) for e in ext.graph["edges"]}
    assert ("astrobee.merge", "astrobee.common") in edges


def test_the_ros_unit_is_env_blocked_not_error() -> None:
    res = run_tier0(find_node(ROOT, "astrobee.stats"), ROOT)
    assert res.verdict == verdicts.ENV_BLOCKED
    assert "rosbag" in res.checks[0].detail


def test_the_merge_unit_is_green_in_a_fresh_process() -> None:
    """Judge/extractor parity: the eval loader mirrors the package map, so
    the unit whose file imports localization_common at module import is
    judgeable WITHOUT a sibling's eval having warmed sys.modules (this was
    order-dependent before the loader learned the map)."""
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "ent.cli", "eval", "astrobee.merge"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GREEN" in proc.stdout


def test_the_latent_bug_row_still_pins_the_crash() -> None:
    """parse_localization_log_str crashes on a value with no trailing unit —
    found by authoring the fixture. If someone fixes the regex upstream this
    verdict flips, which is exactly the alarm the row exists to raise."""
    res = run_tier0(find_node(ROOT, "astrobee.mapping"), ROOT)
    assert res.verdict == verdicts.GREEN
    assert any("CRASHES" in c.detail or "expectError" in c.type for c in res.checks
               if c.status == "pass")
