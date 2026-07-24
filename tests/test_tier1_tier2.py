"""tier1 (golden) + tier2 (LLM judge) eval tests.

Beyond-spec extension. Covers the significance logic (§5.3: red only on
meaningful regression), the humanBlessed gate (§5.2), metric correctness, the
entrypoint resolver, and the judge scaffold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent.evals.entrypoint import EntrypointError, resolve_entrypoint  # noqa: E402
from ent.evals.metrics import accuracy, exact_match, get_metric, ndcg_at_k  # noqa: E402
from ent.evals.runner import run_tier1, run_tier2  # noqa: E402
from ent.manifest import Node, find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def test_exact_match() -> None:
    assert exact_match({"a": 1}, {"a": 1}) == 1.0
    assert exact_match({"a": 1}, {"a": 2}) == 0.0


def test_accuracy_on_labels() -> None:
    assert accuracy({"label": "spam"}, {"label": "spam"}) == 1.0
    assert accuracy({"label": "spam"}, {"label": "ham"}) == 0.0


def test_ndcg_perfect_and_zero() -> None:
    good = {"chunks": [{"id": "a"}, {"id": "b"}]}
    assert ndcg_at_k(good, {"top_ids": ["a"]}, 5) == pytest.approx(1.0)
    bad = {"chunks": [{"id": "x"}]}
    assert ndcg_at_k(bad, {"top_ids": ["a"]}, 5) == 0.0


def test_get_metric_parses_ndcg_k() -> None:
    m = get_metric("ndcg@3")
    assert m({"chunks": [{"id": "a"}]}, {"top_ids": ["a"]}) == pytest.approx(1.0)
    with pytest.raises(KeyError):
        get_metric("bogus")


# --------------------------------------------------------------------------- #
# tier1 — golden scoring
# --------------------------------------------------------------------------- #

def _golden_node(tmp_path: Path, *, blessed: bool = True, baseline: float = 1.0) -> Node:
    (tmp_path / "d.jsonl").write_text(
        '{"input": {"x": 1}, "expected": {"label": "a"}}\n'
        '{"input": {"x": 2}, "expected": {"label": "b"}}\n'
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


def test_tier1_within_band_is_green(tmp_path: Path) -> None:
    node = _golden_node(tmp_path, baseline=1.0)
    # Perfect entrypoint: echoes the label the dataset expects.
    result = run_tier1(node, tmp_path, entrypoint=lambda inp: {"label": "a" if inp["x"] == 1 else "b"})
    assert result.verdict == "green"
    assert "within band" in result.checks[0].detail


def test_tier1_meaningful_regression_is_red(tmp_path: Path) -> None:
    node = _golden_node(tmp_path, baseline=1.0)
    # Always wrong → accuracy 0.0, far below baseline − significance.
    result = run_tier1(node, tmp_path, entrypoint=lambda inp: {"label": "wrong"})
    assert result.verdict == "red"
    assert "regression" in result.checks[0].detail


def test_tier1_requires_human_blessed(tmp_path: Path) -> None:
    node = _golden_node(tmp_path, blessed=False)
    result = run_tier1(node, tmp_path, entrypoint=lambda inp: {"label": "a"})
    assert result.verdict == "red"
    assert "humanBlessed" in result.checks[0].detail


def test_tier1_greenfield_end_to_end() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    result = run_tier1(node, GREENFIELD)  # resolves the real entrypoint
    assert result.verdict == "green"
    assert "ndcg@5" in result.checks[0].detail


# --------------------------------------------------------------------------- #
# tier2 — LLM judge
# --------------------------------------------------------------------------- #

def _judge_node(tmp_path: Path) -> Node:
    (tmp_path / "d.jsonl").write_text('{"input": {"x": 1}, "expected": {"label": "a"}}\n')
    (tmp_path / "r.md").write_text("Rate the answer 1-5.\n")
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
    node = _judge_node(tmp_path)
    result = run_tier2(node, tmp_path, entrypoint=lambda inp: {"label": "a"})
    assert result.checks[0].status == "skip"
    assert "no judge" in result.checks[0].detail


def test_tier2_passes_with_high_scoring_judge(tmp_path: Path) -> None:
    node = _judge_node(tmp_path)
    result = run_tier2(node, tmp_path, judge=lambda i, o, r: 4.5,
                       entrypoint=lambda inp: {"label": "a"})
    assert result.verdict == "green"
    assert "4.5" in result.checks[0].detail


def test_tier2_fails_with_low_scoring_judge(tmp_path: Path) -> None:
    node = _judge_node(tmp_path)
    result = run_tier2(node, tmp_path, judge=lambda i, o, r: 2.0,
                       entrypoint=lambda inp: {"label": "a"})
    assert result.verdict == "red"


# --------------------------------------------------------------------------- #
# entrypoint resolver
# --------------------------------------------------------------------------- #

def test_resolver_finds_greenfield_entrypoint() -> None:
    node = find_node(GREENFIELD, "retrieval.chunk_ranker")
    fn = resolve_entrypoint(node, GREENFIELD)
    out = fn({"query": "q", "candidates": [{"id": "a", "text": "hello"}], "k": 1})
    assert "chunks" in out


def test_resolver_raises_for_missing_entrypoint(tmp_path: Path) -> None:
    (tmp_path / "s.py").write_text("x = 1\n")  # no @ent.node callable
    node = Node.from_manifest(
        {"id": "a.b", "name": "A", "nodeKind": "compute", "owner": "me",
         "claims": ["s.py"], "contract": {"sideEffects": "none"}},
        tmp_path / "entiendo.node.yaml",
    )
    with pytest.raises(EntrypointError):
        resolve_entrypoint(node, tmp_path)
