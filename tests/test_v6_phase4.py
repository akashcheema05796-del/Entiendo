"""PLAN_v6 Phase 4 — ent dev, plugin packaging, a golden for the brain.

4.1's browser suite lives in tests/frontend/frontend_universe.py (NOT collected
    by default pytest — run it explicitly). Here: the unit-testable seams.
4.2 live reload: what gets watched, how change is detected, and the
    last-good-view drift fallback (`resilient_graph`); the `ent dev` alias.
4.3 the Claude Code plugin manifests validate and reference real files; MCP
    elicitation on approval-gated post_verdict settles a proposal in-line, and
    ANY elicitation failure falls back gracefully to the web surface.
4.4 refundly.decide gets a discriminating tier1 golden (baseline 0.80, not a
    saturated 1.0) that goes REGRESSED under a real multi-row regression.
    The dataset stays humanBlessed: false — blessing is Mehar's act alone.
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

from ent import baselines, mcp_server, steering  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.server import resilient_graph, snapshot_mtimes, watched_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def refundly(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


# --------------------------------------------------------------------------- #
# 4.2 live reload seams
# --------------------------------------------------------------------------- #

def test_watched_paths_cover_manifests_claims_and_history(refundly: Path) -> None:
    watched = {str(p) for p in watched_paths(refundly)}
    assert str(refundly / "src/decide/entiendo.node.yaml") in watched     # manifest
    assert str(refundly / "src/decide/agent.py") in watched               # claimed file
    assert str(refundly / "entiendo/history/events.jsonl") in watched     # history


def test_snapshot_detects_touch_and_deletion(refundly: Path) -> None:
    paths = watched_paths(refundly)
    before = snapshot_mtimes(paths)
    target = refundly / "src/decide/agent.py"
    target.write_text(target.read_text() + "\n# touched\n")
    after = snapshot_mtimes(paths)
    assert before != after
    target.unlink()
    assert snapshot_mtimes(paths)[str(target)] is None      # missing → None, no raise


def test_resilient_graph_serves_last_good_view_on_failure() -> None:
    good = {"nodes": [{"id": "a"}], "edges": []}
    # first success primes the cache
    status, payload, cache = resilient_graph(200, good, None)
    assert (status, payload, cache) == (200, good, good)
    # failure with a cache → last good + drift flag, cache intact
    status, payload, cache = resilient_graph(500, {"error": "boom"}, cache)
    assert status == 200 and payload["drift"] == "boom" and payload["nodes"] == good["nodes"]
    assert cache == good
    # failure with NO cache stays an error — nothing good to serve
    status, payload, cache = resilient_graph(500, {"error": "boom"}, None)
    assert status == 500 and cache is None


def test_universe_page_carries_reload_and_drift_wiring() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "watchVersion" in html and "/api/version" in html
    assert "drift-banner" in html and "location.reload()" in html


def test_ent_dev_alias_registers() -> None:
    proc = subprocess.run([sys.executable, "-m", "ent.cli", "dev", "--help"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0 and "live reload" in proc.stdout


# --------------------------------------------------------------------------- #
# 4.3 plugin manifests + elicitation
# --------------------------------------------------------------------------- #

def test_plugin_manifest_validates_and_references_real_files() -> None:
    plugin_dir = REPO_ROOT / ".claude-plugin"
    plugin = json.loads((plugin_dir / "plugin.json").read_text())
    assert plugin["name"] == "entiendo" and plugin["version"]
    assert plugin["mcpServers"]["entiendo"]["command"] == "ent"
    for rel in plugin["skills"]:
        assert (plugin_dir / rel).resolve().is_dir(), f"skill missing: {rel}"
    hook_cmds = [h["command"] for entry in plugin["hooks"]["PreToolUse"]
                 for h in entry["hooks"]]
    assert any("enforce_claims.py" in c for c in hook_cmds)
    assert (REPO_ROOT / ".claude/hooks/enforce_claims.py").is_file()


def test_marketplace_manifest_lists_the_plugin() -> None:
    market = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text())
    assert [p["name"] for p in market["plugins"]] == ["entiendo"]
    assert market["plugins"][0]["source"]


def _gated_outcome(root: Path, marker: str) -> dict:
    target = root / "src/orders/store.py"
    before = target.read_text()
    return {"unit": "refundly.orders",
            "diffs": {"src/orders/store.py":
                      {"before": before, "after": before + f"\n# {marker}\n"}},
            "unifiedDiffs": {"src/orders/store.py": f"+# {marker}"}}


def test_elicited_approve_settles_the_proposal_inline(refundly: Path) -> None:
    asked: list[str] = []

    def elicit(message: str) -> str:
        asked.append(message)
        return "approve"

    res = mcp_server.tool_post_verdict(refundly, "steer-el-1",
                                       _gated_outcome(refundly, "elicited"),
                                       proposal=True, elicit=elicit)
    assert res["status"] == "approved" and res["approval"]["applied"]
    assert asked and "approval-gated" in asked[0]
    assert "# elicited" in (refundly / "src/orders/store.py").read_text()
    assert steering.proposal_for(refundly, "steer-el-1") is None    # settled


def test_elicited_reject_discards_without_applying(refundly: Path) -> None:
    res = mcp_server.tool_post_verdict(refundly, "steer-el-2",
                                       _gated_outcome(refundly, "rejected"),
                                       proposal=True, elicit=lambda m: "reject")
    assert res["status"] == "rejected"
    assert "# rejected" not in (refundly / "src/orders/store.py").read_text()
    assert steering.proposal_for(refundly, "steer-el-2") is None


def test_elicitation_failure_falls_back_to_the_web_surface(refundly: Path) -> None:
    def broken(message: str) -> str:
        raise RuntimeError("client does not support elicitation")

    res = mcp_server.tool_post_verdict(refundly, "steer-el-3",
                                       _gated_outcome(refundly, "fallback"),
                                       proposal=True, elicit=broken)
    assert res["status"] == "awaiting-approval"                     # graceful
    assert steering.proposal_for(refundly, "steer-el-3") is not None
    # an unrecognised answer is the same as no answer
    res2 = mcp_server.tool_post_verdict(refundly, "steer-el-4",
                                        _gated_outcome(refundly, "maybe"),
                                        proposal=True, elicit=lambda m: "maybe later")
    assert res2["status"] == "awaiting-approval"


# --------------------------------------------------------------------------- #
# 4.4 the decide golden
# --------------------------------------------------------------------------- #

def test_decide_golden_discriminates_at_080(refundly: Path) -> None:
    res = run_tier1(find_node(refundly, "refundly.decide"), refundly)
    assert res.verdict == "WITHIN_BAND"
    assert res.advisory is True                      # unblessed → advisory only
    assert res.stats["mean"] == 0.8                  # 2 of 10 rows encode ideal
    assert sorted(set(res.stats["rowScores"])) == [0.0, 1.0]


def test_decide_multi_row_regression_goes_regressed(refundly: Path) -> None:
    node = find_node(refundly, "refundly.decide")
    actual = run_tier1(node, refundly).stats["rowScores"]
    baselines.write_baseline(refundly, "refundly.decide", {
        "baseline": 0.8, "metric": "exact_match", "minRuns": 1,
        "significance": 0.05, "rowScores": [s + 0.5 for s in actual]})
    res = run_tier1(node, refundly)
    assert res.verdict == "REGRESSED"
    assert res.stats["verdictMethod"] == "paired-bootstrap"


def test_decide_dataset_stays_unblessed_for_mehar(refundly: Path) -> None:
    node = find_node(refundly, "refundly.decide")
    golden = next(e for e in node.raw["evals"]["tier1"] if e["type"] == "golden")
    assert golden["humanBlessed"] is False           # NEVER blessed by the AI
    assert baselines.read_bless(refundly, "refundly.decide") is None
    rows = [json.loads(l) for l in
            (refundly / golden["dataset"]).read_text().splitlines() if l.strip()]
    assert len(rows) == 10 and all("expect" in r for r in rows)
