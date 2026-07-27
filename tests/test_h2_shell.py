"""Phase H2 acceptance (PLAN_v4.md) — design system + Universe shell.

Structure tests over the emitted HTML (runtime behaviour verified separately with
Playwright): the celestial-cartography tokens, and the shell features — camera
(zoom/pan), pointer/touch events, search, keyboard, URL state, minimap, and
two-way group collapse. Existing render/universe tests still pass unchanged.
"""

from __future__ import annotations

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.render import build_universe  # noqa: E402


def _html() -> str:
    return build_universe(None)


# --------------------------------------------------------------------------- #
# H2.1 — the design system (celestial cartography)
# --------------------------------------------------------------------------- #

def test_celestial_palette_tokens() -> None:
    html = _html()
    for token in ("--field:#080B14", "--starlight:#F2EFE6", "--hairline:#2A3244",
                  "--annotation:#C9A961", "--signal-green:#3FBF7F",
                  "--signal-amber:#E0A83C", "--signal-red:#E05252"):
        assert token in html, token


def test_type_families() -> None:
    html = _html()
    assert "Fraunces" in html and "Inter" in html and "IBM Plex Mono" in html
    assert "--font-display" in html and "--font-mono" in html


def test_orbital_interior_signature() -> None:
    html = _html()
    # satellites drawn on an orbit ring inside an agentic unit, tethered to crossings
    assert "u.interior && u.interior.tools" in html
    assert "orbit" in html and "crosses" in html


# --------------------------------------------------------------------------- #
# H2.2 — the shell
# --------------------------------------------------------------------------- #

def test_camera_zoom_pan() -> None:
    html = _html()
    for fn in ("screenToWorld", "zoomAt", "flyTo", "fitToView", "cam.scale"):
        assert fn in html


def test_pointer_and_touch_events() -> None:
    html = _html()
    for ev in ("pointerdown", "pointermove", "pointerup", "wheel"):
        assert f"'{ev}'" in html
    assert "pinchDist" in html and "pointers" in html      # pinch-to-zoom
    assert "mousedown" not in html and "mousemove" not in html  # replaced by pointer events


def test_search_jump() -> None:
    html = _html()
    assert 'id="search-input"' in html
    assert "openSearch" in html and "function fuzzy" in html and "jumpTo" in html


def test_keyboard_access() -> None:
    html = _html()
    assert "'keydown'" in html
    assert "Tab" in html and "'/'" in html and "focusIdx" in html
    assert 'tabindex="0"' in html                          # canvas is focusable


def test_url_state() -> None:
    html = _html()
    assert "applyUrlState" in html and "writeUrlState" in html
    assert "location.hash" in html and "unit=" in html and "hashchange" in html


def test_minimap() -> None:
    html = _html()
    assert 'id="minimap"' in html and "drawMinimap" in html
    assert "cam.scale>1.5" in html                         # shows past 1.5x


def test_two_way_group_collapse() -> None:
    html = _html()
    assert 'id="recollapse"' in html                       # dedicated re-collapse control
    assert "'dblclick'" in html and "expanded.delete" in html  # dbl-click hull re-collapses
    assert "expanded.add" in html                          # click container expands


def test_reduced_motion_camera() -> None:
    html = _html()
    # camera flights snap instantly under reduced motion
    assert "if (RM){ Object.assign(cam, target)" in html


def test_empty_state_invites_init() -> None:
    html = _html()
    assert 'id="empty"' in html and "ent init" in html
