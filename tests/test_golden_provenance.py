"""Oracle-class provenance — the tautological-oracle guard (research round 2, rec F).

Harvested oracles capture *actual* behaviour, not *expected* behaviour: an
expected value derived from the implementation can only ever agree with it.
So every golden row may declare where its expected value came from, harvested
rows are tagged implementation-derived by construction, and blessing a dataset
containing such rows is an explicit flagged choice — never a default.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import goldens  # noqa: E402
from ent.fixtures import propose_from_traces  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
GOLDEN = "evals/refundly.decide/golden_v3.jsonl"


# --------------------------------------------------------------------------- #
# the classifier itself
# --------------------------------------------------------------------------- #

def test_classes_and_the_unknown_default() -> None:
    assert goldens.row_class({"oracleClass": "contract-derivable"}) == "contract-derivable"
    assert goldens.row_class({"oracleClass": "implementation-derived"}) == "implementation-derived"
    assert goldens.row_class({}) == "unknown"                       # legacy rows
    assert goldens.row_class({"oracleClass": "vibes"}) == "unknown"  # never promoted


def test_census_and_quarantine() -> None:
    rows = [{"name": "a", "oracleClass": "contract-derivable"},
            {"name": "b", "oracleClass": "implementation-derived"},
            {"name": "c"}]
    c = goldens.census(rows)
    assert c == {"contract-derivable": 1, "implementation-derived": 1, "unknown": 1}
    assert goldens.quarantined(rows) == ["b"]
    assert "1 implementation-derived" in goldens.describe(c)


# --------------------------------------------------------------------------- #
# the teeth: ent bless
# --------------------------------------------------------------------------- #

def _bless(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ent.cli", "bless", "refundly.decide",
         "--as", "mehar@example.com", "--yes", *extra],
        cwd=str(root), capture_output=True, text=True, timeout=60)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def _retag(project: Path, name: str, cls: str) -> None:
    p = project / GOLDEN
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    for r in rows:
        if r["name"] == name:
            r["oracleClass"] = cls
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_blessing_quarantined_rows_is_refused_without_the_flag(project: Path) -> None:
    """The refusal names the rows and the remedy, and fires BEFORE the TTY
    gate — so even a would-be interactive bless learns about the tautology
    first."""
    _retag(project, "within-policy-clear", "implementation-derived")
    proc = _bless(project)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "implementation-derived" in proc.stdout
    assert "within-policy-clear" in proc.stdout
    assert "--accept-implementation-derived" in proc.stdout


def test_the_accept_flag_moves_on_to_the_human_gate(project: Path) -> None:
    """With the flag, the tautology is consciously accepted — and the NEXT
    gate (interactive TTY) takes over. Non-interactive still cannot bless."""
    _retag(project, "within-policy-clear", "implementation-derived")
    proc = _bless(project, "--accept-implementation-derived")
    assert proc.returncode == 3                       # the TTY gate, not the quarantine
    assert "interactive" in proc.stdout


def test_clean_dataset_hits_the_tty_gate_directly(project: Path) -> None:
    """refundly's shipped goldens are spec-first (tagged contract-derivable):
    no quarantine, straight to the human gate."""
    proc = _bless(project)
    assert proc.returncode == 3
    assert "interactive" in proc.stdout


# --------------------------------------------------------------------------- #
# provenance at the source: harvested rows are tagged by construction
# --------------------------------------------------------------------------- #

def test_harvested_fixture_rows_carry_their_provenance() -> None:
    props = propose_from_traces(REFUNDLY, "refundly.decide")
    assert props
    for p in props:
        assert p.fixture["provenance"] == "trace-harvest"
        assert p.fixture["oracleClass"] == "implementation-derived"


def test_shipped_goldens_are_tagged_contract_derivable() -> None:
    rows = [json.loads(l)
            for l in (REPO_ROOT / "examples/refundly" / GOLDEN).read_text().splitlines()
            if l.strip()]
    assert rows and all(r.get("oracleClass") == "contract-derivable" for r in rows)
