"""PLAN_v6 Phase 2 — enforced boundary + honest health.

2.1 the enforce_claims PreToolUse hook (script-level, real subprocess + JSON
    payloads): unclaimed → deny; other unit while steered → deny; steered unit's
    file → allow; unmanaged repo → allow (fail-open).
2.2 the health lens data contract: build_view carries the latest tier1
    statistical verdict (statVerdict + CI + n) for units with tier1 history.
(2.3 lives in tests/test_h5_live_bridge.py; 2.4 is scripts/demo_reset.sh.)
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

from ent import steering  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.extractor import extract, write_artifacts  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.render import build_view  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
HOOK = REPO_ROOT / ".claude" / "hooks" / "enforce_claims.py"


@pytest.fixture()
def managed(tmp_path: Path) -> Path:
    """A scratch refundly with entiendo/graph.json present (a managed repo)."""
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


# --------------------------------------------------------------------------- #
# 2.1 the hook
# --------------------------------------------------------------------------- #

def test_unclaimed_file_is_denied(managed: Path) -> None:
    (managed / "rogue.py").write_text("x = 1\n")             # no claim, no acknowledgment
    out = _hook(managed, str(managed / "rogue.py"))
    assert _decision(out) == "deny"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "UNCLAIMED" in reason and "claims" in reason      # actionable


def test_acknowledged_unclaimed_file_is_allowed(managed: Path) -> None:
    """Invariant 4 has two legitimate states: claimed, or EXPLICITLY unclaimed.
    refundly's entiendo/unclaimed.txt acknowledges README.md — glue like that
    (a repo's tests, docs) must stay editable, and a NEW file matching an
    acknowledged glob is editable too (patterns, not the frozen expansion)."""
    assert _decision(_hook(managed, str(managed / "README.md"))) == "allow"
    fresh = managed / "evals" / "brand_new.jsonl"            # matches evals/*
    assert _decision(_hook(managed, str(fresh))) == "allow"


def test_other_units_file_denied_while_steered(managed: Path) -> None:
    steering.enqueue(managed, "refundly.parse_email", "tighten the regex")
    out = _hook(managed, str(managed / "src" / "gateway" / "client.py"))
    assert _decision(out) == "deny"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "refundly.gateway" in reason and "refundly.parse_email" in reason


def test_steered_units_file_is_allowed(managed: Path) -> None:
    steering.enqueue(managed, "refundly.gateway", "clamp the refund")
    out = _hook(managed, str(managed / "src" / "gateway" / "client.py"))
    assert _decision(out) == "allow"


def test_claimed_file_allowed_when_no_steer_active(managed: Path) -> None:
    out = _hook(managed, str(managed / "src" / "gateway" / "client.py"))
    assert _decision(out) == "allow"                         # only unclaimed denied


def test_unmanaged_repo_fails_open(tmp_path: Path) -> None:
    (tmp_path / "anything.py").write_text("x = 1\n")
    out = _hook(tmp_path, str(tmp_path / "anything.py"))
    assert _decision(out) == "allow"                         # no graph.json → allow


def test_plane_owned_paths_are_always_allowed(managed: Path) -> None:
    steering.enqueue(managed, "refundly.gateway", "clamp")
    # a manifest (boundary change, human-reviewed) and an eval fixture
    for p in (managed / "src" / "orders" / "entiendo.node.yaml",
              managed / "evals" / "refundly.parse_email" / "golden_v3.jsonl"):
        assert _decision(_hook(managed, str(p))) == "allow"


def test_hook_is_registered_in_settings() -> None:
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    pre = settings["hooks"]["PreToolUse"]
    assert any("enforce_claims.py" in h["command"]
               for entry in pre for h in entry["hooks"])
    # every editor write tool is matched (Phase-2 hardening added NotebookEdit)
    matchers = [entry["matcher"] for entry in pre]
    assert any(all(tool in m for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"))
               for m in matchers)


# --------------------------------------------------------------------------- #
# 2.2 health-lens data contract
# --------------------------------------------------------------------------- #

def test_build_view_carries_latest_tier1_stat_verdict(managed: Path) -> None:
    node = find_node(managed, "refundly.parse_email")
    run_tier1(node, managed)                                 # records into evals.jsonl
    view = build_view(managed)
    unit = next(n for n in view["nodes"] if n["id"] == "refundly.parse_email")
    t1 = unit["tier1"]
    assert t1 is not None and t1["statVerdict"] == "WITHIN_BAND"
    assert "verdictMethod" in t1 and "nRows" in t1
    # units with no tier1 history carry None — absence is explicit, not implied
    gateway = next(n for n in view["nodes"] if n["id"] == "refundly.gateway")
    assert gateway["tier1"] is None
