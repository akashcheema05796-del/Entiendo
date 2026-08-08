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
