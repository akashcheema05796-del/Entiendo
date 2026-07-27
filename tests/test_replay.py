"""Phase E acceptance (PLAN_v3.md §E) — fingerprint replay + pin + timeline deltas.

- bump a model string → replay shows the delta attributed to `model` only;
- pin writes the manifest and moves the fingerprint; pinning back restores it;
- history records the events; the Timeline annotates each tick's changed dims.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import history, render, replay as replay_mod  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.version import compute_version, pin_model  # noqa: E402


def _runnable_node(tmp_path: Path, model: str = "model-a") -> Path:
    """A tier1-runnable self-contained unit with a model dimension."""
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'y': req['x']}\n")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "golden.jsonl").write_text('{"input": {"x": 1}, "expect": {"y": 1}}\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.thing\nname: Demo\nnodeKind: compute\n"
        "owner: me\nclaims: [mod.py]\n"
        "version:\n  model: " + model + "\n"
        "contract:\n  entrypoint: mod.py::run\n  invariants: []\n  sideEffects: none\n"
        "evals:\n  tier1:\n    - type: golden\n      dataset: evals/golden.jsonl\n"
        "      humanBlessed: true\n      metric: exact_match\n      baseline: 1.0\n      minRuns: 1\n")
    return tmp_path


# --------------------------------------------------------------------------- #
# pure pieces
# --------------------------------------------------------------------------- #

def test_dimension_diff() -> None:
    old = {"code": "a", "prompt": None, "config": None, "model": "x"}
    cur = {"code": "a", "prompt": None, "config": None, "model": "y"}
    assert replay_mod.dimension_diff(old, cur) == ["model"]


def test_resolve_fingerprint_by_prefix(tmp_path: Path) -> None:
    history.append_version(tmp_path, "demo.thing", {"code": "a", "model": "x", "composite": "abc123"})
    got = replay_mod.resolve_fingerprint(tmp_path, "demo.thing", "abc")
    assert got and got["composite"] == "abc123" and got["version"]["model"] == "x"
    assert replay_mod.resolve_fingerprint(tmp_path, "demo.thing", "zzz") is None


# --------------------------------------------------------------------------- #
# pin
# --------------------------------------------------------------------------- #

def test_pin_moves_and_restores_fingerprint(tmp_path: Path) -> None:
    root = _runnable_node(tmp_path, model="model-a")
    node = find_node(root, "demo.thing")
    fp_a = compute_version(node, root)["composite"]

    prev = pin_model(node.path, "model-b")
    assert prev == "model-a"
    fp_b = compute_version(find_node(root, "demo.thing"), root)["composite"]
    assert fp_b != fp_a                       # the fingerprint moved

    pin_model(node.path, "model-a")           # pin back
    fp_a2 = compute_version(find_node(root, "demo.thing"), root)["composite"]
    assert fp_a2 == fp_a                       # restored


# --------------------------------------------------------------------------- #
# replay — the model-bump acceptance
# --------------------------------------------------------------------------- #

def test_replay_attributes_delta_to_model_only(tmp_path: Path) -> None:
    root = _runnable_node(tmp_path, model="model-a")
    node = find_node(root, "demo.thing")
    fp_a = compute_version(node, root)
    history.append_version(root, "demo.thing", fp_a)     # record the old fingerprint

    pin_model(node.path, "model-b")                      # bump the model string

    result = replay_mod.replay(root, "demo.thing", fp_a["composite"])
    assert result["changedDimensions"] == ["model"]      # attributed to model only
    assert result["attribution"] == "model"
    # code/prompt/config unchanged → identical artifacts → the metric delta is 0
    assert result["delta"] == 0.0
    assert result["verdict"] == "WITHIN_BAND"
    assert result["current"]["score"] == 1.0


def test_replay_unknown_fingerprint_errors(tmp_path: Path) -> None:
    root = _runnable_node(tmp_path)
    assert "error" in replay_mod.replay(root, "demo.thing", "deadbeef")


# --------------------------------------------------------------------------- #
# timeline dimension deltas
# --------------------------------------------------------------------------- #

def test_annotate_fingerprint_deltas() -> None:
    timelines = {
        "demo.thing": [
            {"kind": "version", "composite": "c1", "version": {"code": "a", "model": "x"}},
            {"kind": "eval", "verdict": "green"},
            {"kind": "version", "composite": "c2", "version": {"code": "a", "model": "y"}},
            {"kind": "version", "composite": "c3", "version": {"code": "b", "model": "y"}},
        ]
    }
    render._annotate_fingerprint_deltas(timelines)
    ticks = [e for e in timelines["demo.thing"] if e["kind"] == "version"]
    assert ticks[0]["changed"] == []            # initial
    assert ticks[1]["changed"] == ["model"]     # x → y
    assert ticks[2]["changed"] == ["code"]      # a → b


def test_build_view_exposes_timeline_deltas(tmp_path: Path) -> None:
    root = _runnable_node(tmp_path)
    node = find_node(root, "demo.thing")
    v1 = compute_version(node, root)
    history.append_version(root, "demo.thing", v1)
    pin_model(node.path, "model-z")
    v2 = compute_version(find_node(root, "demo.thing"), root)
    history.append_version(root, "demo.thing", v2)

    view = render.build_view(root)
    ticks = [e for e in view["timelines"]["demo.thing"] if e["kind"] == "version"]
    assert ticks[-1]["changed"] == ["model"]
