"""What the landing view tells an operator before they click anything.

Driving the live surface turned up three orientation failures: the system's
health appeared nowhere on screen (you had to open every unit or decode ring
styles to learn most were untested), a 14-unit repo opened as six abstract
group boxes, and the first paint caught the camera still easing in from a
corner. These guard the wiring that fixed them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = REPO_ROOT / "src/ent/universe.html"


def test_summary_states_the_health_tally() -> None:
    html = UNIVERSE.read_text()
    assert "tally[n.health" in html, "the summary must count units by verdict"
    # worst-first ordering: an operator should read RED before GREEN
    assert "['RED','ERROR','DEGRADED','UNSTABLE','UNTESTED','GREEN']" in html


def test_landing_does_not_collapse_a_mid_size_repo() -> None:
    html = UNIVERSE.read_text()
    assert "COLLAPSE_THRESHOLD = 24" in html


def test_first_paint_is_already_framed() -> None:
    """fitToView starts an eased flight; the boot path must land on the target
    rather than showing the map drifting in."""
    html = UNIVERSE.read_text()
    assert "if (cam.flight){ Object.assign(cam, cam.flight); cam.flight = null; }" in html


def test_header_cannot_grow_into_the_centred_lens_bar() -> None:
    html = UNIVERSE.read_text()
    assert "width:calc(50% - 300px)" in html, "the left cluster must be bounded"
    # and the mobile rules must come AFTER the base #lenses rule to take effect
    assert html.index("#lenses { position:fixed") < html.index("@media (max-width: 980px)")


def test_layered_dag_is_the_default_layout() -> None:
    """Research rec A: force-directed layouts lose to layered DAGs for
    comprehension — every tool developers keep open defaults to layered LR.
    Constellation survives as the toggle, not the default."""
    html = UNIVERSE.read_text()
    assert "let layoutMode='layered';" in html
    assert "setLayout('constellation'" in html or "'constellation':'layered'" in html
    # first paint IS the finished DAG — no glide-in from random positions
    assert "u.x=u._tx; u.y=u._ty;" in html
    # ranked columns are labelled
    assert "drawLayerLabels" in html and "foundations" in html


def test_focus_cone_scopes_the_map() -> None:
    """Research rec A: 'blast-radius-scoped subgraph views matter more than
    the layout algorithm itself'. `f` (or the impact tab's button) scopes the
    map to one unit's upstream+downstream cone; everything else fades."""
    html = UNIVERSE.read_text()
    assert "function focusCone(id)" in html and "function clearFocus()" in html
    assert "wfocus-btn" in html                       # reachable from the window
    assert "press f to clear" in html                 # and the exit is stated
