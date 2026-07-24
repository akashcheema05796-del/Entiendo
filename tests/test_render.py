"""L4 render tests (Phase 4).

Acceptance (SPEC.md §8, Phase 4): health colour matches `ent eval` output. The
render model computes health via the same run_tier0, so this is guaranteed — the
test locks it in. Also checks structure + timeline data end up in the view/HTML.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent import history  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.render import build_view, render_html  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def test_view_has_all_nodes_and_edges() -> None:
    view = build_view(GREENFIELD)
    assert len(view["nodes"]) == 5
    assert view["edges"]
    assert view["reconciled"] is True


def test_health_matches_ent_eval() -> None:
    view = build_view(GREENFIELD)
    for n in view["nodes"]:
        node = find_node(GREENFIELD, n["id"])
        expected = run_tier0(node, GREENFIELD).verdict
        assert n["health"] == expected


def test_nodes_carry_composite_version() -> None:
    view = build_view(GREENFIELD)
    for n in view["nodes"]:
        assert n["version"]["composite"]


def test_render_html_is_self_contained_and_lists_nodes() -> None:
    view = build_view(GREENFIELD)
    html = render_html(view)
    assert html.startswith("<!doctype html>")
    assert "http://" not in html.split("<script")[0]  # no external resources in head/body
    for n in view["nodes"]:
        assert n["id"] in html


def test_timeline_reflects_recorded_history(tmp_path: Path) -> None:
    # A tiny project so build_view reads our recorded events.
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "mod").mkdir()
    manifest = tmp_path / "mod" / "entiendo.node.yaml"
    manifest.write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: a.one\nname: A\nnodeKind: compute\n"
        "owner: me\nclaims: [a.py]\ncontract: {sideEffects: none}\n"
        "evals: {tier0: [{type: invariant_check}]}\n"
    )
    history.append_eval(tmp_path, "a.one", "green", 0, commit="c0", ts="t0")

    view = build_view(tmp_path)
    assert view["timelines"]["a.one"]
    assert any(e["kind"] == "eval" for e in view["timelines"]["a.one"])
