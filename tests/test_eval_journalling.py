"""`ent eval` records what it found.

The flight recorder only recorded when `ent snapshot` ran, so the history tab
and the timeline lens were permanently empty for anyone who never discovered
that command — the most common act in the tool (running an eval) left no trace.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import history  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def _eval(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ent.cli", "eval", *args],
                          cwd=str(root), capture_output=True, text=True, timeout=120)


def _evals_for(root: Path, node_id: str) -> list[dict]:
    return [e for e in history.timeline(root, node_id) if e.get("kind") == "eval"]


def test_eval_records_its_verdict(project: Path) -> None:
    before = len(_evals_for(project, "refundly.parse_email"))
    proc = _eval(project, "refundly.parse_email")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = _evals_for(project, "refundly.parse_email")
    assert len(after) == before + 1
    event = after[-1]
    assert event["verdict"] in {"GREEN", "RED", "UNTESTED", "ERROR"}
    assert event["tier"] == 0
    assert event["kind"] == "eval"


def test_no_journal_records_nothing(project: Path) -> None:
    before = len(_evals_for(project, "refundly.parse_email"))
    proc = _eval(project, "refundly.parse_email", "--no-journal")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(_evals_for(project, "refundly.parse_email")) == before


def test_eval_all_records_every_unit(project: Path) -> None:
    _eval(project, "--all")
    recorded = {e["nodeId"] for e in history.read_events(project)
                if e.get("kind") == "eval"}
    assert {"refundly.decide", "refundly.parse_email", "refundly.orders"} <= recorded


def test_journalling_never_rewrites_history(project: Path) -> None:
    """Append-only is the law: earlier lines survive byte-identical."""
    events_file = project / "entiendo" / "history" / "events.jsonl"
    original = events_file.read_text()
    _eval(project, "--all")
    assert events_file.read_text().startswith(original)
