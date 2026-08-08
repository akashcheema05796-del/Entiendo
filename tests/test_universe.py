"""Phase B acceptance (PLAN_v3.md §B): the Universe is THE render surface.

DOM-structure tests over the emitted HTML (no browser): the field, kind-forms,
health, flow particles, reduced-motion, group-collapse, and the logic-first
dossier fields (task / contract / verdict / fingerprint / edges / artifacts) that
each end in an action (steer / revert / approve). Also: static `ent render`
embeds the data; `ent serve` hydrates from `/api/graph`; a 50-node synthetic
view renders with groups collapsed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.render import build_universe, build_view, render_html  # noqa: E402
from ent.server import build_app_html  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _embedded(html: str) -> dict:
    m = re.search(r'<script id="view" type="application/json">(.*?)</script>', html, re.S)
    assert m, "no embedded view block"
    return json.loads(m.group(1))


# --------------------------------------------------------------------------- #
# the field + kind-forms + health + motion
# --------------------------------------------------------------------------- #

def test_universe_is_the_render_surface() -> None:
    html = render_html(build_view(GREENFIELD))
    assert html.startswith("<!doctype html>")
    assert 'id="universe"' in html            # the canvas field
    assert "the Universe" in html


def test_kind_forms_are_distinct_silhouettes() -> None:
    html = build_universe(None)
    # Deep-Space Instrument: silhouette-first kind encoding —
    # chip / cylinder / hex / tag / cut-corner / container
    for form in ("chip", "cylinder", "hex", "tag", "cut", "container"):
        assert f"'{form}'" in html
    assert "drawSilhouette" in html and "drawKindGlyph" in html
    # external stays gold and is the ONLY dashed silhouette
    assert "--gold" in html
    # health is shape too, never colour alone (status-ring styles)
    assert "drawStatusRing" in html
    for style in ("double", "dotted", "broken", "marching"):
        assert style in html


def test_flow_particles_and_verified_vs_declared() -> None:
    html = build_universe(None)
    assert "particles" in html
    assert "e.verified" in html               # verified = bright/fast, declared = dim/dashed
    assert "setLineDash" in html


def test_reduced_motion_supported() -> None:
    html = build_universe(None)
    assert "prefers-reduced-motion" in html
    assert "RM" in html                       # the reduced-motion guard


def test_six_lens_toggles_present() -> None:
    html = build_universe(None)
    # assert the lens IDS, not the button copy — the labels are user-facing
    # prose and get rewritten for plainness; the ids are the stable contract.
    for lens in ("structure", "flow", "trace", "health", "timeline", "blast"):
        assert f'data-lens="{lens}"' in html


# --------------------------------------------------------------------------- #
# the logic-first dossier — task, contract, verdict, fingerprint, edges; then
# artifacts (collapsed); ending in an action.
# --------------------------------------------------------------------------- #

def test_unit_window_is_logic_first_with_all_fields() -> None:
    """Everything the docked panel carried is still reachable, under plain
    names and one tab per question."""
    html = build_universe(None)
    assert 'id="dossier"' not in html            # the panel is gone, not hidden
    for tab in ("inside", "identity", "promises", "checks", "history", "impact"):
        assert f"tab==='{tab}'" in html
    assert "Files it owns" in html               # claims, in words
    assert "Version" in html and "composite" in html


def test_a_unit_can_be_acted_on() -> None:
    html = build_universe(None)
    for action in (">Steer<", ">Revert<", ">Approve<"):
        assert action in html
    assert "async function winSteer" in html and "async function winRevert" in html


def test_blast_radius_tint_on_select() -> None:
    html = build_universe(None)
    assert "computeBlast" in html             # transitive downstream dependents
    assert "blast" in html


def test_steer_wired_to_the_bridge() -> None:
    """Phase C: Steer enqueues via /api/steer and polls /api/steering."""
    html = build_universe(None)
    assert "/api/steer" in html               # enqueue a steering request
    assert "/api/steering" in html            # poll for the posted verdict
    assert "winSteerPoll" in html             # the window watches for the verdict
    assert ".flash" in html                   # the bubble flashes when it lands


# --------------------------------------------------------------------------- #
# two modes: static embed vs live hydrate
# --------------------------------------------------------------------------- #

def test_static_render_embeds_the_view() -> None:
    view = build_view(GREENFIELD)
    data = _embedded(render_html(view))
    assert len(data["nodes"]) == len(view["nodes"])
    ids = {n["id"] for n in data["nodes"]}
    assert "retrieval.chunk_ranker" in ids


def test_static_render_carries_dossier_data_per_unit() -> None:
    data = _embedded(render_html(build_view(GREENFIELD)))
    ranker = next(n for n in data["nodes"] if n["id"] == "retrieval.chunk_ranker")
    assert ranker["task"]                     # a task line
    assert ranker["invariants"]               # contract invariants
    assert ranker["claims"]                   # artifacts
    assert ranker["version"]["composite"]     # fingerprint


def test_serve_mode_hydrates_from_api_not_embedded() -> None:
    html = build_app_html()
    assert html.startswith("<!doctype html>")
    assert "/api/graph" in html
    # the embedded block is the literal null → the page fetches instead
    assert '<script id="view" type="application/json">null</script>' in html


def test_embedded_json_is_script_safe() -> None:
    payload_html = render_html(build_view(GREENFIELD))
    block = re.search(r'application/json">(.*?)</script>', payload_html, re.S).group(1)
    assert "<" not in block and ">" not in block   # escaped as < / >
    json.loads(block)                              # still valid JSON


# --------------------------------------------------------------------------- #
# scale: 50-node synthetic view renders with group-collapse
# --------------------------------------------------------------------------- #

def test_fifty_node_view_renders_with_group_collapse() -> None:
    nodes = []
    for i in range(50):
        g = f"group{i % 6}"
        nodes.append({
            "id": f"{g}.unit{i}", "name": f"unit{i}", "nodeKind": "compute", "group": g,
            "owner": "me", "status": "active", "claims": [f"src/{g}/u{i}.py"],
            "sideEffects": "none", "approvalRequired": False,
            "health": "GREEN", "healthColour": "green",
            "version": {"composite": f"v{i}"}, "task": f"do thing {i}", "invariants": [],
        })
    view = {"apiVersion": "entiendo/v1", "commit": None,
            "coverage": {"coverage": 1.0}, "nodes": nodes, "edges": [],
            "reconciled": True, "executable": 50, "nodeCount": 50,
            "timelines": {}, "traces": [], "traffic": {}}
    html = build_universe(view)
    # Collapse kicks in above 24 units. It was 12, which hid a 14-unit repo
    # behind six abstract group boxes on landing — small and mid-size repos
    # should show their actual units.
    assert "COLLAPSE_THRESHOLD = 24" in html
    data = _embedded(html)
    assert len(data["nodes"]) == 50
    assert len({n["group"] for n in data["nodes"]}) == 6


def test_city_lens_is_wired() -> None:
    html = build_universe(None)
    # v7 Code City: territory = truth — area is real file mass
    assert 'data-lens="city"' in html
    assert "buildCity" in html and "drawCity" in html and "cityHit" in html
    assert "claimedFileCount" in html          # mass comes from expanded claims
