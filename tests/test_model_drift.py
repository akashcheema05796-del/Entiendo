"""Model-drift enforcement (research rec C, part 2).

The manifest pins a model (`version.model` — a fingerprint dimension); the app
reports what actually answered (`gen_ai.response.model`, via the OTel reader).
A silent model swap is a behaviour change nobody reviewed: `ent ci` fails it
(severity 1) until the human fixes the app or accepts the swap with `ent pin` —
which moves the composite fingerprint, making the swap a diffable version.

The market alerts on drift; almost nobody makes it a build failure with a
versioned accept path. That asymmetry is the point.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent.ci import run_ci  # noqa: E402
from ent.otel import ingest, model_drift  # noqa: E402
from ent.version import compute_version, pin_model  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"

DECIDE = "refundly.decide"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    # isolate from the deliberate gateway cost overage (budget showcase)
    gpath = dest / "src/gateway/entiendo.node.yaml"
    gdoc = yaml.safe_load(gpath.read_text())
    gdoc.setdefault("budgets", {})["costPerCallUsd"] = 0.10
    gpath.write_text(yaml.safe_dump(gdoc, sort_keys=False))
    return dest


def _observe(project: Path, tmp_path: Path, model: str) -> None:
    span = {"name": DECIDE, "spanId": "s1", "traceId": "t1",
            "startTimeUnixNano": "0", "endTimeUnixNano": "1000000",
            "attributes": [
                {"key": "gen_ai.response.model", "value": {"stringValue": model}},
                {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "10"}},
            ]}
    f = tmp_path / "obs.json"
    f.write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}))
    ingest(project, f)


def _pin(project: Path, model: str) -> None:
    pin_model(project / "src/decide/entiendo.node.yaml", model)


def _model_stage(project: Path):
    return next(s for s in run_ci(project).stages if s.name == "model")


def test_pinned_and_matching_passes(project: Path, tmp_path: Path) -> None:
    _pin(project, "claude-sonnet-5")
    _observe(project, tmp_path, "claude-sonnet-5")
    stage = _model_stage(project)
    assert stage.ok and "1 pinned unit(s) match" in stage.detail


def test_dated_response_matches_undated_pin(project: Path, tmp_path: Path) -> None:
    """Providers report dated ids; a pin of the alias accepts its dated forms —
    one way only. This mirrors 'pin everything you can' without forcing the
    manifest to chase date suffixes."""
    _pin(project, "claude-sonnet-5")
    _observe(project, tmp_path, "claude-sonnet-5-20260114")
    assert _model_stage(project).ok


def test_undeclared_swap_fails_the_build(project: Path, tmp_path: Path) -> None:
    _pin(project, "claude-sonnet-5")
    _observe(project, tmp_path, "gpt-4o-2024-08-06")
    result = run_ci(project)
    stage = next(s for s in result.stages if s.name == "model")
    assert not stage.ok
    assert stage.exit_severity == 1 and result.exit_code == 1
    w = " ".join(stage.warnings)
    assert DECIDE in w and "gpt-4o-2024-08-06" in w and "ent pin" in w


def test_dated_pin_accepts_nothing_looser(project: Path, tmp_path: Path) -> None:
    """A dated pin is exact: the bare alias answering is a swap too (the alias
    can move under you — that is the whole reason to date the pin)."""
    _pin(project, "claude-sonnet-5-20260114")
    _observe(project, tmp_path, "claude-sonnet-5")
    assert not _model_stage(project).ok


def test_unpinned_observations_warn_but_never_block(project: Path, tmp_path: Path) -> None:
    _observe(project, tmp_path, "claude-sonnet-5")
    stage = _model_stage(project)
    assert stage.ok and stage.exit_severity == 0
    assert any("consider" in w and "ent pin" in w for w in stage.warnings)


def test_accepting_the_swap_moves_the_fingerprint(project: Path, tmp_path: Path) -> None:
    """The differentiated behaviour: accepting a swap is a VERSION, not a
    silenced alert. `ent pin` changes the model dimension, the composite moves,
    and the model stage goes green — a diffable, reviewable state change."""
    _pin(project, "claude-sonnet-5")
    _observe(project, tmp_path, "gpt-4o-2024-08-06")
    before = compute_version(find_node(project, DECIDE), project)
    assert not _model_stage(project).ok

    _pin(project, "gpt-4o-2024-08-06")                 # the human accepts
    after = compute_version(find_node(project, DECIDE), project)
    assert _model_stage(project).ok
    assert after["model"] == "gpt-4o-2024-08-06"
    assert after["composite"] != before["composite"]   # a real version bump


def test_no_observations_is_not_judged(project: Path) -> None:
    stage = _model_stage(project)
    assert stage.ok and "no model observations" in stage.detail


def test_drift_rows_carry_the_full_story(project: Path, tmp_path: Path) -> None:
    _pin(project, "claude-sonnet-5")
    _observe(project, tmp_path, "gpt-4o-2024-08-06")
    row = next(r for r in model_drift(project) if r["unit"] == DECIDE)
    assert row["status"] == "drift"
    assert row["declared"] == "claude-sonnet-5"
    assert row["offending"] == ["gpt-4o-2024-08-06"]
