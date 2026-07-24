"""L3 versioning + history tests (Phase 4).

Acceptance (SPEC.md §8, Phase 4): a node's version change is visible on the
timeline within one commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ent import history
from ent.manifest import Node
from ent.version import compute_version


def _node(tmp_path: Path, claims: dict[str, str], *, model: str | None = None) -> Node:
    for rel, content in claims.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    raw = {
        "id": "demo.node", "name": "Demo", "nodeKind": "compute", "owner": "me",
        "claims": list(claims),
        "contract": {"sideEffects": "none"},
    }
    if model:
        raw["version"] = {"model": model}
    return Node.from_manifest(raw, tmp_path / "entiendo.node.yaml")


# --------------------------------------------------------------------------- #
# version
# --------------------------------------------------------------------------- #

def test_version_is_deterministic(tmp_path: Path) -> None:
    node = _node(tmp_path, {"a.py": "x = 1\n", "p.md": "prompt\n"})
    v1 = compute_version(node, tmp_path)
    v2 = compute_version(node, tmp_path)
    assert v1 == v2
    assert v1["code"] and v1["prompt"] and v1["composite"]


def test_code_change_changes_composite(tmp_path: Path) -> None:
    node = _node(tmp_path, {"a.py": "x = 1\n"})
    before = compute_version(node, tmp_path)["composite"]
    (tmp_path / "a.py").write_text("x = 2\n")
    after = compute_version(node, tmp_path)["composite"]
    assert before != after


def test_model_is_a_version_dimension(tmp_path: Path) -> None:
    a = _node(tmp_path, {"a.py": "x = 1\n"}, model="claude-sonnet-4-6")
    va = compute_version(a, tmp_path)["composite"]
    b = _node(tmp_path, {"a.py": "x = 1\n"}, model="claude-opus-4-8")
    vb = compute_version(b, tmp_path)["composite"]
    assert va != vb


# --------------------------------------------------------------------------- #
# history
# --------------------------------------------------------------------------- #

def test_version_events_dedup(tmp_path: Path) -> None:
    node = _node(tmp_path, {"a.py": "x = 1\n"})
    v = compute_version(node, tmp_path)
    first = history.append_version(tmp_path, node.id, v, commit="c0", ts="t0")
    dup = history.append_version(tmp_path, node.id, v, commit="c0", ts="t0")
    assert first is not None
    assert dup is None  # unchanged composite → not recorded again


def test_version_change_appears_on_timeline(tmp_path: Path) -> None:
    node = _node(tmp_path, {"a.py": "x = 1\n"})
    history.append_version(tmp_path, node.id, compute_version(node, tmp_path), commit="c0", ts="t0")

    (tmp_path / "a.py").write_text("x = 2\n")  # a change within the next commit
    changed = history.append_version(tmp_path, node.id, compute_version(node, tmp_path), commit="c1", ts="t1")

    assert changed is not None
    versions = [e for e in history.timeline(tmp_path, node.id) if e["kind"] == "version"]
    assert len(versions) == 2
    assert versions[0]["composite"] != versions[1]["composite"]
    assert [e["seq"] for e in versions] == sorted(e["seq"] for e in versions)


def test_eval_events_always_append(tmp_path: Path) -> None:
    history.append_eval(tmp_path, "demo.node", "green", 0, commit="c0", ts="t0")
    history.append_eval(tmp_path, "demo.node", "green", 0, commit="c0", ts="t0")
    evals = [e for e in history.timeline(tmp_path, "demo.node") if e["kind"] == "eval"]
    assert len(evals) == 2


def test_timeline_filters_by_node(tmp_path: Path) -> None:
    history.append_eval(tmp_path, "a.one", "green", 0)
    history.append_eval(tmp_path, "b.two", "red", 0)
    assert all(e["nodeId"] == "a.one" for e in history.timeline(tmp_path, "a.one"))
    assert len(history.timeline(tmp_path)) == 2
