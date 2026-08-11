"""The oracle boundary — the verifier's state is mechanically agent-unwritable.

Research (propose-verify architecture, rec A): the single most-validated
finding across propose-verify systems is that the proposer must be
*mechanically prevented* from writing the verifier's state — agents
demonstrably game evals by editing the evaluator (METR's o3 monkey-patching
the scorer; ImpossibleBench's direct test modification; SWE-Bench+ solution
leakage). "Isolate the agent from the evaluator" is the non-negotiable.

These are the adversarial-Builder tests: every write an agent could use to
fake a green build is denied by the claims hook, and the paths the hook
cannot govern are covered by content signatures that void on tamper.
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

from ent.baselines import (  # noqa: E402
    blessing_valid,
    dataset_sha256,
    write_bless,
)
from ent.extractor import extract, write_artifacts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
HOOK = REPO_ROOT / ".claude" / "hooks" / "enforce_claims.py"

GOLDEN = "evals/refundly.decide/golden_v3.jsonl"


@pytest.fixture()
def managed(tmp_path: Path) -> Path:
    root = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, root)
    write_artifacts(extract(root), root)
    return root


def _hook(root: Path, file_path: str) -> dict:
    payload = {"tool_name": "Edit", "cwd": str(root),
               "tool_input": {"file_path": file_path}}
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _decision(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "allow")


def _reason(out: dict) -> str:
    return out["hookSpecificOutput"]["permissionDecisionReason"]


# --------------------------------------------------------------------------- #
# the oracle paths are denied — every lever the reward-hacking literature
# documents, mapped to its Entiendo analogue
# --------------------------------------------------------------------------- #

def test_history_is_not_agent_writable(managed: Path) -> None:
    """Rewriting the append-only record = forging verdicts and observations
    (the trace events the model-drift gate reads live here too)."""
    out = _hook(managed, str(managed / "entiendo" / "history" / "events.jsonl"))
    assert _decision(out) == "deny"
    assert "append-only" in _reason(out)


def test_baselines_and_blessings_are_not_agent_writable(managed: Path) -> None:
    """Editing a baseline moves the goalpost; forging a .bless.json forges the
    human signature itself."""
    base = managed / "entiendo" / "baselines"
    for name in ("refundly.decide.json", "refundly.decide.pending.json",
                 "refundly.decide.bless.json"):
        out = _hook(managed, str(base / name))
        assert _decision(out) == "deny", name
        assert "ent bless" in _reason(out) or "ent baseline" in _reason(out)


def test_generated_map_artifacts_are_not_agent_writable(managed: Path) -> None:
    """Invariant 1 (the map is generated, never drawn), now mechanical: editing
    graph.json directly could grant claims or erase drift without extraction."""
    for name in ("graph.json", "coverage.json"):
        out = _hook(managed, str(managed / "entiendo" / name))
        assert _decision(out) == "deny", name
        assert "ent extract" in _reason(out)


def test_steering_state_is_not_agent_writable(managed: Path) -> None:
    """Verdicts enter through post_verdict (idempotent, own process) — writing
    results/<id>.json directly would fake a completed steer."""
    out = _hook(managed,
                str(managed / "entiendo" / "steering" / "results" / "r1.json"))
    assert _decision(out) == "deny"
    assert "post_verdict" in _reason(out)


def test_blessed_golden_dataset_is_denied_other_fixtures_stay_editable(
        managed: Path, tmp_path: Path) -> None:
    """The tautological-oracle guard: once a human signs a golden dataset, an
    editor write to it is denied by name — while ordinary (unblessed) tier-0
    fixtures remain freely authorable, as eval authorship policy intends."""
    dataset = managed / GOLDEN
    assert dataset.exists()
    write_bless(managed, "refundly.decide", dataset_rel=GOLDEN,
                sha=dataset_sha256(dataset), rows=3,
                blessed_by="mehar@example.com", blessed_at="2026-08-11T00:00:00Z")
    out = _hook(managed, str(dataset))
    assert _decision(out) == "deny"
    assert "blessed" in _reason(out) and "ent bless" in _reason(out)
    # an unblessed fixture in the same tree is still editable
    smoke = managed / "evals" / "refundly.decide" / "smoke.jsonl"
    assert _decision(_hook(managed, str(smoke))) == "allow"


def test_tampering_around_the_hook_still_voids_the_blessing(managed: Path) -> None:
    """Defense in depth: the hook only governs editor tools. A write that
    bypasses it (shell, plain open()) voids the content signature, so the
    tier-1 gate stops treating the dataset as blessed."""
    dataset = managed / GOLDEN
    write_bless(managed, "refundly.decide", dataset_rel=GOLDEN,
                sha=dataset_sha256(dataset), rows=3,
                blessed_by="mehar@example.com", blessed_at="2026-08-11T00:00:00Z")
    assert blessing_valid(managed, "refundly.decide", dataset)
    with open(dataset, "a", encoding="utf-8") as fh:      # around the hook
        fh.write('{"name": "smuggled", "input": {}, "expected": {}}\n')
    assert not blessing_valid(managed, "refundly.decide", dataset)


# --------------------------------------------------------------------------- #
# the boundary is a scalpel, not a wall — everything legitimate stays open
# --------------------------------------------------------------------------- #

def test_proposal_surfaces_remain_editable(managed: Path) -> None:
    """Manifests and acknowledged glue are the agent's PROPOSAL surface (they
    are reviewed in PRs) — the oracle deny must not creep into them."""
    assert _decision(_hook(
        managed, str(managed / "src" / "decide" / "entiendo.node.yaml"))) == "allow"
    assert _decision(_hook(managed, str(managed / "README.md"))) == "allow"
    assert _decision(_hook(
        managed, str(managed / "src" / "gateway" / "client.py"))) == "allow"


def test_fail_open_outside_managed_repos(tmp_path: Path) -> None:
    """An ordinary repo (no entiendo/graph.json) is untouched — even for paths
    that would be oracle paths in a managed tree."""
    plain = tmp_path / "plain"
    (plain / "entiendo" / "history").mkdir(parents=True)
    out = _hook(plain, str(plain / "entiendo" / "history" / "events.jsonl"))
    assert _decision(out) == "allow"


def test_unreadable_bless_record_does_not_brick_the_session(managed: Path) -> None:
    """A corrupt .bless.json must not make the hook crash or deny everything:
    the dataset falls back to ordinary rules (and the signature — being
    unreadable — simply never validates, so tier-1 treats it as unblessed)."""
    bless = managed / "entiendo" / "baselines" / "refundly.decide.bless.json"
    bless.parent.mkdir(parents=True, exist_ok=True)
    bless.write_text("{not json")
    smoke = managed / "evals" / "refundly.decide" / "smoke.jsonl"
    assert _decision(_hook(managed, str(smoke))) == "allow"
