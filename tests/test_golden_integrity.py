"""The golden hash manifest — adversarial tests (hardening Phase 1).

Every documented tamper route against ground truth must be caught loudly:
byte edits, rogue additions, deletions, and a hand-edited lock. The trust
root is git + CI review, so the code-level guarantee under test is exactly:
no mismatch between disk and lock can ever grade, and every legitimate
change is forced through a reviewable lock diff.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import integrity  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
GOLDEN = "evals/refundly.decide/golden_v3.jsonl"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    integrity.write_lock(dest)                       # freshly pinned
    return dest


def _verify(root: Path) -> str:
    integrity._VERIFIED.discard(str(root.resolve()))  # defeat the process cache
    return integrity.verify_manifest(root)


# --------------------------------------------------------------------------- #
# adversarial: every tamper route is caught, naming the file
# --------------------------------------------------------------------------- #

def test_a_single_flipped_byte_is_caught(project: Path) -> None:
    p = project / GOLDEN
    p.write_bytes(p.read_bytes().replace(b'"amount": 42', b'"amount": 43', 1))
    with pytest.raises(integrity.GoldenTamperError) as err:
        _verify(project)
    assert GOLDEN in str(err.value) and "changed" in str(err.value)


def test_a_rogue_golden_is_caught_even_though_no_manifest_declares_it(project: Path) -> None:
    rogue = project / "evals" / "refundly.decide" / "golden_planted.jsonl"
    rogue.write_text('{"name": "free-pass", "input": {}, "expect": {}}\n')
    with pytest.raises(integrity.GoldenTamperError) as err:
        _verify(project)
    assert "golden_planted.jsonl" in str(err.value) and "added" in str(err.value)


def test_a_deleted_golden_is_caught(project: Path) -> None:
    (project / GOLDEN).unlink()
    with pytest.raises(integrity.GoldenTamperError) as err:
        _verify(project)
    assert GOLDEN in str(err.value) and "missing" in str(err.value)


def test_hand_editing_the_lock_cannot_hide_a_tamper_from_review(project: Path) -> None:
    """The lock-forgery route: tamper a golden AND rewrite its lock entry.
    Local verify then passes (lock and disk agree) — by design: the code
    cannot distinguish forgery from a legitimate re-bless. What defeats it is
    that the lock is a COMMITTED file: the forged entry is a diff a PR
    reviewer sees, and CI re-verifies from the merged lock. The invariant the
    code must hold: the forged lock differs from the blessed one."""
    blessed = (project / integrity.LOCK_REL).read_text()
    p = project / GOLDEN
    p.write_bytes(p.read_bytes().replace(b'"amount": 42', b'"amount": 4200', 1))
    doc = json.loads(blessed)
    doc["files"][GOLDEN] = integrity._sha256(p)      # the forgery
    (project / integrity.LOCK_REL).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    assert _verify(project)                          # locally consistent…
    assert (project / integrity.LOCK_REL).read_text() != blessed  # …but never invisible


def test_a_corrupt_lock_is_fatal_not_ignored(project: Path) -> None:
    (project / integrity.LOCK_REL).write_text("{not json")
    with pytest.raises(integrity.GoldenTamperError):
        _verify(project)


# --------------------------------------------------------------------------- #
# the wiring: grading refuses tampered ground truth
# --------------------------------------------------------------------------- #

def test_tier1_grading_is_fatal_on_tamper(project: Path) -> None:
    p = project / GOLDEN
    p.write_bytes(p.read_bytes().replace(b'"amount": 42', b'"amount": 999', 1))
    integrity._VERIFIED.discard(str(project.resolve()))
    result = run_tier1(find_node(project, "refundly.decide"), project)
    assert result.verdict == "ERROR"
    err = next(c for c in result.checks if c.type == "integrity")
    assert "goldens.lock" in err.detail


def test_verification_is_cached_per_process(project: Path) -> None:
    integrity._VERIFIED.discard(str(project.resolve()))
    integrity.ensure_verified(project)
    # tamper AFTER the cached check: the same process no longer rehashes
    (project / GOLDEN).write_text("tampered\n")
    integrity.ensure_verified(project)               # cached → no raise
    with pytest.raises(integrity.GoldenTamperError):
        _verify(project)                             # a fresh check still catches it


# --------------------------------------------------------------------------- #
# the CLI + CI gate
# --------------------------------------------------------------------------- #

def _cli(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    e = {**os.environ, **(env or {})}
    e.pop("ENTIENDO_CI", None) if env is None else None
    return subprocess.run([sys.executable, "-m", "ent.cli", "goldens", *args],
                          cwd=str(root), capture_output=True, text=True,
                          timeout=120, env=e)


def test_cli_verify_exits_1_on_mismatch_0_when_clean(project: Path) -> None:
    assert _cli(project, "verify", "--require-lock").returncode == 0
    (project / GOLDEN).write_text("tampered\n")
    proc = _cli(project, "verify")
    assert proc.returncode == 1 and "TAMPER" in proc.stdout


def test_bless_refuses_under_ci(project: Path) -> None:
    proc = _cli(project, "bless", env={"ENTIENDO_CI": "1"})
    assert proc.returncode == 3
    assert "refusing under CI" in proc.stdout
    proc = _cli(project, "bless", env={"CI": "1"})
    assert proc.returncode == 3


def test_bless_warns_that_it_repins_ground_truth(project: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "ENTIENDO_CI")}
    proc = subprocess.run([sys.executable, "-m", "ent.cli", "goldens", "bless"],
                          cwd=str(project), capture_output=True, text=True,
                          timeout=120, env=env)
    assert proc.returncode == 0
    assert "GROUND TRUTH" in proc.stdout and "PR review" in proc.stdout


def test_a_repo_with_no_goldens_passes_and_require_lock_bites(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    assert "nothing pinned" in integrity.verify_manifest(bare)
    # goldens exist but nobody pinned them: only --require-lock makes that fatal
    (bare / "evals" / "x").mkdir(parents=True)
    (bare / "evals" / "x" / "golden_v1.jsonl").write_text("{}\n")
    assert integrity.verify_manifest(bare)           # visible-unprotected passes
    with pytest.raises(integrity.GoldenTamperError):
        integrity.verify_manifest(bare, require_lock=True)
