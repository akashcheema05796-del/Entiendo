"""PLAN_v6 Phase 1 — honest verdicts, safe writes.

1.1 the sandboxed runner (a hostile node cannot hang or balloon the suite),
1.2 paired-bootstrap statistics (a test, not a threshold — with an honest
    UNSTABLE when underpowered), 1.3 the base-hash guard on proposal approve,
1.4 the single claims authority (realpath + containment, no string compares).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import baselines, claims, mcp_server, sandbox, steering  # noqa: E402
from ent.editloop import check_boundary  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
GREENFIELD = REPO_ROOT / "examples" / "greenfield"

MANIFEST = """apiVersion: entiendo/v1
kind: Node
id: {id}
name: {id}
nodeKind: compute
owner: me
claims:
  - {claim}
contract:
  entrypoint: {claim}::go
  sideEffects: none
evals:
  timeoutMs: 2000
  tier0:
    - {{type: smoke, fixture: evals/f.jsonl}}
"""


def _hostile(tmp_path: Path, node_id: str, body: str) -> Path:
    (tmp_path / "mod").mkdir()
    (tmp_path / "mod" / "code.py").write_text(body)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "f.jsonl").write_text('{"name":"r1","input":{}}\n')
    (tmp_path / "mod" / "entiendo.node.yaml").write_text(
        MANIFEST.format(id=node_id, claim="mod/code.py"))
    return tmp_path


# --------------------------------------------------------------------------- #
# 1.1 sandbox
# --------------------------------------------------------------------------- #

def test_hung_node_times_out_without_hanging_the_suite(tmp_path: Path) -> None:
    root = _hostile(tmp_path, "evil.hang", "def go(req):\n    while True:\n        pass\n")
    node = find_node(root, "evil.hang")
    start = time.perf_counter()
    result = sandbox.run_sandboxed(root, node, 0)
    elapsed = time.perf_counter() - start
    assert result["verdict"] == "ERROR"
    assert "TIER0_TIMEOUT" in result["checks"][0]["detail"]
    assert elapsed < 10                                   # killed at ~2s (timeoutMs)


def test_overallocating_node_is_bounded(tmp_path: Path) -> None:
    root = _hostile(tmp_path, "evil.balloon",
                    "def go(req):\n    x = bytearray(1024*1024*1024)\n    return {'ok': True}\n")
    node = find_node(root, "evil.balloon")
    result = sandbox.run_sandboxed(root, node, 0)
    # under RLIMIT_AS the child raises MemoryError (RED via execute-fail) or, if
    # the platform can't set the limit, the wall clock still bounds it (ERROR).
    assert result["verdict"] in ("RED", "ERROR")


def test_green_node_passes_sandboxed_under_latency_budget() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    start = time.perf_counter()
    result = sandbox.run_sandboxed(GREENFIELD, node, 0)
    assert result["verdict"] == "GREEN"                   # same verdict as in-process
    assert time.perf_counter() - start < 2.0              # <2s per node (plan budget)


def test_manifest_timeout_override_is_honored(tmp_path: Path) -> None:
    root = _hostile(tmp_path, "evil.hang", "def go(req):\n    while True:\n        pass\n")
    node = find_node(root, "evil.hang")
    assert sandbox.timeout_for(node, 0) == 2.0            # evals.timeoutMs: 2000
    plain = find_node(GREENFIELD, "retrieval.chunk_ranker")
    assert sandbox.timeout_for(plain, 0) == 5.0 and sandbox.timeout_for(plain, 1) == 30.0


# --------------------------------------------------------------------------- #
# 1.2 paired-bootstrap statistics
# --------------------------------------------------------------------------- #

@pytest.fixture()
def refundly(tmp_path: Path) -> Path:
    root = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, root)
    return root


def _seed_baseline(root: Path) -> list[float]:
    node = find_node(root, "refundly.parse_email")
    r = run_tier1(node, root)
    rows = r.stats["rowScores"]
    baselines.write_baseline(root, "refundly.parse_email", {
        "baseline": r.stats["mean"], "metric": "exact_match",
        "minRuns": 3, "significance": 0.05, "rowScores": rows})
    return rows


def test_legacy_baseline_without_rowscores_uses_threshold(refundly: Path) -> None:
    node = find_node(refundly, "refundly.parse_email")
    r = run_tier1(node, refundly)                         # manifest baseline only
    assert r.stats["verdictMethod"] == "threshold-legacy"
    assert r.verdict == "WITHIN_BAND"


def test_identical_run_is_within_band_with_ci(refundly: Path) -> None:
    _seed_baseline(refundly)
    node = find_node(refundly, "refundly.parse_email")
    r = run_tier1(node, refundly)
    assert r.stats["verdictMethod"] == "paired-bootstrap"
    assert r.verdict == "WITHIN_BAND"
    assert r.stats["ciLow"] == 0.0 and r.stats["ciHigh"] == 0.0
    assert r.stats["nRows"] == 9 and "minDetectableEffect" in r.stats


def test_multirow_regression_is_regressed_with_ci_below_zero(refundly: Path) -> None:
    _seed_baseline(refundly)
    node = find_node(refundly, "refundly.parse_email")

    def broken(req):                                      # fails every row
        return {"orderId": None, "reason": "?"}

    r = run_tier1(node, refundly, entrypoint=broken)
    assert r.verdict == "REGRESSED"
    assert r.stats["ciHigh"] < 0                          # CI entirely below zero


def test_single_row_regression_is_honestly_unstable(refundly: Path) -> None:
    # one bad row among nine is NOT significant at this n — the old threshold
    # would have screamed REGRESSED; the bootstrap says "underpowered".
    _seed_baseline(refundly)
    node = find_node(refundly, "refundly.parse_email")

    def one_worse(req):
        import re
        m = re.search(r"\border\s+(\w+)", req.get("email", ""))   # case-sensitive
        return {"orderId": m.group(1) if m else None, "reason": req.get("reason", "unspecified")}

    r = run_tier1(node, refundly, entrypoint=one_worse)
    assert r.verdict == "UNSTABLE"
    assert r.stats["ciLow"] < 0 <= r.stats["ciHigh"]      # straddles zero


def test_bootstrap_is_deterministic(refundly: Path) -> None:
    _seed_baseline(refundly)
    node = find_node(refundly, "refundly.parse_email")
    a = run_tier1(node, refundly).stats
    b = run_tier1(node, refundly).stats
    assert (a["ciLow"], a["ciHigh"]) == (b["ciLow"], b["ciHigh"])   # fixed seed


# --------------------------------------------------------------------------- #
# 1.3 base-hash guard on approve
# --------------------------------------------------------------------------- #

NEW_GATEWAY = "def execute_refund(order_id, amount, order_amount=None):\n" \
              "    capped = min(amount, order_amount) if order_amount is not None else amount\n" \
              "    return {'order': order_id, 'refunded': capped, 'irreversible': True}\n"


def _propose(root: Path) -> str:
    req = steering.enqueue(root, "refundly.gateway", "clamp the refund")
    res = mcp_server.tool_apply_edit(root, "refundly.gateway", "clamp",
                                     [{"path": "src/gateway/client.py", "content": NEW_GATEWAY}])
    mcp_server.tool_post_verdict(root, req["id"], res, proposal=True)
    return req["id"]


def test_stale_proposal_is_refused_with_zero_writes(refundly: Path) -> None:
    rid = _propose(refundly)
    target = refundly / "src" / "gateway" / "client.py"
    # the tree moves underneath the proposal
    mutated = target.read_text() + "\n# hotfix landed while proposal was open\n"
    target.write_text(mutated)

    result = steering.approve(refundly, rid)
    assert "error" in result and "stale" in result["error"]
    assert target.read_text() == mutated                  # zero writes — tree untouched
    assert steering.proposals(refundly)                   # proposal still open


def test_clean_approve_still_applies(refundly: Path) -> None:
    rid = _propose(refundly)
    result = steering.approve(refundly, rid)
    assert result.get("applied") == ["src/gateway/client.py"]
    assert "order_amount" in (refundly / "src" / "gateway" / "client.py").read_text()


# --------------------------------------------------------------------------- #
# 1.4 the single claims authority
# --------------------------------------------------------------------------- #

def test_dotdot_escape_is_rejected(refundly: Path) -> None:
    node = find_node(refundly, "refundly.gateway")
    assert not claims.is_within_claims(refundly, node, "../outside.py")
    assert not claims.is_within_claims(refundly, node, "src/gateway/../../../etc/passwd")


def test_symlink_claim_out_of_repo_authorises_nothing(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    root = tmp_path / "repo"
    (root / "mod").mkdir(parents=True)
    os.symlink(outside, root / "mod" / "link.py")         # claim IS a symlink out
    (root / "mod" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: a.one\nname: a.one\n"
        "nodeKind: compute\nowner: me\nclaims:\n  - mod/link.py\n"
        "contract:\n  sideEffects: none\n")
    node = find_node(root, "a.one")
    assert not claims.is_within_claims(root, node, "mod/link.py")
    assert claims.resolved_claims(root, node) == {}       # the claim itself is void


def test_legit_claimed_file_is_allowed(refundly: Path) -> None:
    node = find_node(refundly, "refundly.gateway")
    assert claims.claimed_rel(refundly, node, "src/gateway/client.py") == "src/gateway/client.py"
    # absolute form resolves to the same claim
    assert claims.claimed_rel(refundly, node, refundly / "src/gateway/client.py") \
        == "src/gateway/client.py"


def test_all_three_call_sites_reject_an_escape(refundly: Path) -> None:
    node = find_node(refundly, "refundly.gateway")
    # mcp_server.tool_apply_edit
    res = mcp_server.tool_apply_edit(refundly, "refundly.gateway", "escape",
                                     [{"path": "../evil.py", "content": "x"}])
    assert "error" in res and not (refundly.parent / "evil.py").exists()
    # editloop.check_boundary
    b = check_boundary(node, ["../evil.py"], refundly)
    assert not b.within_claims and b.violations
    # and the claims module itself (server._edit routes through claimed_rel)
    assert claims.claimed_rel(refundly, node, "../evil.py") is None
