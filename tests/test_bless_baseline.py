"""Blessing + baseline promotion (Phase 7 §7, §8).

Blessing signs dataset *content*; editing a row voids it. Baseline promotion is
always a human step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent import baselines, verdicts  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.manifest import Node  # noqa: E402


def _blessed_node(tmp_path: Path) -> tuple[Node, Path]:
    ds = tmp_path / "golden.jsonl"
    ds.write_text(
        '{"name": "a", "input": {"x": 1}, "expect": {"label": "a"}}\n'
        '{"name": "b", "input": {"x": 2}, "expect": {"label": "b"}}\n'
    )
    raw = {
        "id": "demo.node", "name": "Demo", "nodeKind": "compute", "owner": "me",
        "claims": ["s.py"], "contract": {"sideEffects": "none"},
        "evals": {"tier1": [{
            "type": "golden", "dataset": "golden.jsonl", "humanBlessed": True,
            "metric": "accuracy", "baseline": 1.0, "minRuns": 3, "significance": 0.05,
        }]},
    }
    return Node.from_manifest(raw, tmp_path / "entiendo.node.yaml"), ds


# --------------------------------------------------------------------------- #
# blessing
# --------------------------------------------------------------------------- #

def test_blessing_valid_then_void_on_change(tmp_path: Path) -> None:
    _, ds = _blessed_node(tmp_path)
    sha = baselines.dataset_sha256(ds)
    baselines.write_bless(tmp_path, "demo.node", dataset_rel="golden.jsonl", sha=sha,
                          rows=2, blessed_by="tester", blessed_at="t0")
    assert baselines.blessing_valid(tmp_path, "demo.node", ds)

    ds.write_text(ds.read_text() + '{"name": "c", "input": {"x": 3}, "expect": {"label": "c"}}\n')
    assert not baselines.blessing_valid(tmp_path, "demo.node", ds)  # voided


def test_tier1_gates_only_when_blessed(tmp_path: Path) -> None:
    node, ds = _blessed_node(tmp_path)
    good = lambda i: {"label": "a" if i["x"] == 1 else "b"}

    # Unblessed → advisory.
    assert run_tier1(node, tmp_path, entrypoint=good).advisory is True

    # Bless the exact content → gating.
    baselines.write_bless(tmp_path, "demo.node", dataset_rel="golden.jsonl",
                          sha=baselines.dataset_sha256(ds), rows=2,
                          blessed_by="tester", blessed_at="t0")
    result = run_tier1(node, tmp_path, entrypoint=good)
    assert result.advisory is False
    assert result.verdict == verdicts.WITHIN_BAND


# --------------------------------------------------------------------------- #
# baseline promotion
# --------------------------------------------------------------------------- #

def test_pending_then_accept(tmp_path: Path) -> None:
    baselines.write_pending(tmp_path, "demo.node", {"baseline": 0.9, "metric": "accuracy"})
    assert baselines.read_baseline(tmp_path, "demo.node") is None  # not active yet
    promoted = baselines.accept_pending(tmp_path, "demo.node")
    assert promoted["baseline"] == 0.9
    assert baselines.read_baseline(tmp_path, "demo.node")["baseline"] == 0.9
    assert baselines.read_pending(tmp_path, "demo.node") is None  # consumed


def test_improved_run_writes_pending_proposal(tmp_path: Path) -> None:
    node, ds = _blessed_node(tmp_path)
    baselines.write_bless(tmp_path, "demo.node", dataset_rel="golden.jsonl",
                          sha=baselines.dataset_sha256(ds), rows=2,
                          blessed_by="t", blessed_at="t0")
    # baseline 1.0 in config but override active baseline low so the run improves.
    baselines.write_baseline(tmp_path, "demo.node",
                             {"baseline": 0.5, "metric": "accuracy", "minRuns": 3, "significance": 0.05})
    result = run_tier1(node, tmp_path, entrypoint=lambda i: {"label": "a" if i["x"] == 1 else "b"})
    assert result.verdict == verdicts.IMPROVED
    assert baselines.read_pending(tmp_path, "demo.node") is not None
