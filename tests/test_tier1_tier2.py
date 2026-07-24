"""tier1 golden scoring + statistics + tier2 judge (Phase 7 §6, §7).

Covers the metrics, the anti-flicker statistics (§7), advisory blessing (§8),
and the tier2 judge scaffold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent import verdicts  # noqa: E402
from ent.evals.entrypoint import EntrypointError, resolve_entrypoint  # noqa: E402
from ent.evals.metrics import accuracy, contains, exact_match, f1, get_metric, ndcg_at_k  # noqa: E402
from ent.evals.runner import _stat_verdict, run_tier1, run_tier2  # noqa: E402
from ent.manifest import Node, find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def test_metrics() -> None:
    assert exact_match({"a": 1}, {"a": 1}) == 1.0
    assert accuracy({"label": "x"}, {"label": "x"}) == 1.0
    assert ndcg_at_k({"chunks": [{"id": "a"}]}, {"top_ids": ["a"]}, 5) == pytest.approx(1.0)
    assert f1({"items": [1, 2]}, {"items": [2, 3]}) == pytest.approx(0.5)
    assert contains({"text": "hello world"}, {"text": "world"}) == 1.0


def test_get_metric_and_custom() -> None:
    assert get_metric("ndcg@3")({"chunks": [{"id": "a"}]}, {"top_ids": ["a"]}) == pytest.approx(1.0)
    with pytest.raises(KeyError):
        get_metric("bogus")


# --------------------------------------------------------------------------- #
# statistics (§7) — unit-tested directly for determinism
# --------------------------------------------------------------------------- #

def test_stat_within_band() -> None:
    v, _ = _stat_verdict(mean=0.83, baseline=0.81, spread=0.01, sig=0.03)
    assert v == verdicts.WITHIN_BAND


def test_stat_regressed() -> None:
    v, _ = _stat_verdict(mean=0.71, baseline=0.81, spread=0.01, sig=0.03)
    assert v == verdicts.REGRESSED


def test_stat_improved() -> None:
    v, _ = _stat_verdict(mean=0.91, baseline=0.81, spread=0.01, sig=0.03)
    assert v == verdicts.IMPROVED


def test_stat_unstable_when_noisy() -> None:
    # delta beyond significance but within run-to-run spread → can't judge.
    v, _ = _stat_verdict(mean=0.90, baseline=0.81, spread=0.20, sig=0.03)
    assert v == verdicts.UNSTABLE


# --------------------------------------------------------------------------- #
# tier1 runner
# --------------------------------------------------------------------------- #

def _golden_node(tmp_path: Path, *, baseline: float, blessed: bool = True) -> Node:
    (tmp_path / "d.jsonl").write_text(
        '{"name": "a", "input": {"x": 1}, "expect": {"label": "a"}}\n'
        '{"name": "b", "input": {"x": 2}, "expect": {"label": "b"}}\n'
    )
    raw = {
        "id": "demo.node", "name": "Demo", "nodeKind": "compute", "owner": "me",
        "claims": ["s.py"], "contract": {"sideEffects": "none"},
        "evals": {"tier1": [{
            "type": "golden", "dataset": "d.jsonl", "humanBlessed": blessed,
            "metric": "accuracy", "baseline": baseline, "minRuns": 3, "significance": 0.05,
        }]},
    }
    return Node.from_manifest(raw, tmp_path / "entiendo.node.yaml")


def test_tier1_within_band(tmp_path: Path) -> None:
    node = _golden_node(tmp_path, baseline=1.0)
    result = run_tier1(node, tmp_path, entrypoint=lambda i: {"label": "a" if i["x"] == 1 else "b"})
    assert result.verdict == verdicts.WITHIN_BAND


def test_tier1_regressed(tmp_path: Path) -> None:
    node = _golden_node(tmp_path, baseline=1.0)
    result = run_tier1(node, tmp_path, entrypoint=lambda i: {"label": "wrong"})
    assert result.verdict == verdicts.REGRESSED


def test_tier1_unblessed_is_advisory(tmp_path: Path) -> None:
    node = _golden_node(tmp_path, baseline=1.0, blessed=False)
    result = run_tier1(node, tmp_path, entrypoint=lambda i: {"label": "wrong"})
    assert result.advisory is True  # runs, but never gates


def test_tier1_greenfield_end_to_end() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    result = run_tier1(node, GREENFIELD)  # resolves the real entrypoint
    assert result.stats["mean"] == pytest.approx(1.0)
    assert result.advisory is True  # not blessed in the committed example


# --------------------------------------------------------------------------- #
# tier2
# --------------------------------------------------------------------------- #

def _judge_node(tmp_path: Path) -> Node:
    (tmp_path / "d.jsonl").write_text('{"name": "a", "input": {"x": 1}, "expect": {"label": "a"}}\n')
    (tmp_path / "r.md").write_text("Rate 1-5.\n")
    raw = {
        "id": "demo.node", "name": "Demo", "nodeKind": "compute", "owner": "me",
        "claims": ["s.py"], "contract": {"sideEffects": "none"},
        "evals": {
            "tier1": [{"type": "golden", "dataset": "d.jsonl", "humanBlessed": True,
                       "metric": "accuracy", "baseline": 1.0}],
            "tier2": [{"type": "llm_judge", "rubric": "r.md", "sampleSize": 5}],
        },
    }
    return Node.from_manifest(raw, tmp_path / "entiendo.node.yaml")


def test_tier2_skips_without_judge(tmp_path: Path) -> None:
    result = run_tier2(_judge_node(tmp_path), tmp_path, entrypoint=lambda i: {"label": "a"})
    assert result.verdict == verdicts.UNTESTED


def test_tier2_pass_and_fail(tmp_path: Path) -> None:
    node = _judge_node(tmp_path)
    hi = run_tier2(node, tmp_path, judge=lambda i, o, r: 4.5, entrypoint=lambda i: {"label": "a"})
    lo = run_tier2(node, tmp_path, judge=lambda i, o, r: 2.0, entrypoint=lambda i: {"label": "a"})
    assert hi.verdict == verdicts.GREEN
    assert lo.verdict == verdicts.RED


# --------------------------------------------------------------------------- #
# entrypoint resolver (contract.entrypoint)
# --------------------------------------------------------------------------- #

def test_resolver_uses_contract_entrypoint() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    fn = resolve_entrypoint(node, GREENFIELD)
    out = fn({"query": "q", "candidates": [{"id": "a", "text": "hello"}], "k": 1})
    assert "chunks" in out


def test_resolver_raises_without_entrypoint() -> None:
    node = find_node(GREENFIELD, "state.doc_index")  # no contract.entrypoint
    with pytest.raises(EntrypointError):
        resolve_entrypoint(node, GREENFIELD)
