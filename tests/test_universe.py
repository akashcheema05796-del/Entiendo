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


def test_kind_forms_and_gold_diamond() -> None:
    html = build_universe(None)
    # orb / ringed / dashed / gold diamond / container — the kind-form vocabulary
    for form in ("orb", "ring", "ring2", "dashed", "diamond", "container"):
        assert form in html
    assert "--gold" in html                   # external is the gold diamond


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
    for label in ("Structure", "Flow", "Trace", "Health", "Timeline", "Blast radius"):
        assert label in html


# --------------------------------------------------------------------------- #
# the logic-first dossier — task, contract, verdict, fingerprint, edges; then
# artifacts (collapsed); ending in an action.
# --------------------------------------------------------------------------- #

def test_dossier_is_logic_first_with_all_fields() -> None:
    html = build_universe(None)
    assert 'id="dossier"' in html
    for field in ("Task", "Contract", "Verdict", "Fingerprint", "Edges"):
        assert f">{field}</h3>" in html
    # artifacts (claims) collapsed behind a disclosure, AFTER the logic
    assert 'details class="artifacts' in html
    assert "Artifacts —" in html


def test_dossier_ends_in_an_action() -> None:
    html = build_universe(None)
    for action in (">Steer<", ">Revert<", ">Approve<"):
        assert action in html
    assert "function steer" in html and "function revert" in html


def test_blast_radius_tint_on_select() -> None:
    html = build_universe(None)
    assert "computeBlast" in html             # transitive downstream dependents
    assert "blast" in html


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
    assert "COLLAPSE_THRESHOLD = 12" in html   # collapse kicks in above 12 units
    data = _embedded(html)
    assert len(data["nodes"]) == 50
    assert len({n["group"] for n in data["nodes"]}) == 6
