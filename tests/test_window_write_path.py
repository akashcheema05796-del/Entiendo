"""The v7 window can act, not only read.

PLAN_v7 made the floating window the primary surface, but Steer / Approve /
Reject / Revert existed only in the legacy `#dossier` side panel — open a
window and there was no way to act on that unit. Two surfaces for the same
thing, one of them read-only.

These are wiring guards (the live click-through runs in the Playwright suite).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = (REPO_ROOT / "src/ent/universe.html").read_text()


def test_steer_is_a_window_tab() -> None:
    assert "'impact','steer'" in UNIVERSE.replace('"', "'")


def test_window_actions_are_scoped_to_their_own_unit() -> None:
    """Every write takes the window's unit id — never the canvas selection —
    so two open windows cannot act on each other's unit."""
    for fn in ("async function winSteer(unitId, el)",
               "async function winRevert(unitId, el)",
               "async function winSettle(unitId, el, pid, action)"):
        assert fn in UNIVERSE, fn
    # the legacy panel's globals must not leak into the window path
    win_block = UNIVERSE[UNIVERSE.index("async function winSteer"):
                         UNIVERSE.index("async function winProposals")]
    assert "selected" not in win_block, "window actions must not read the canvas selection"


def test_window_write_path_is_delegated_not_rebound() -> None:
    """The body re-renders on every tab switch, so per-render listeners would
    go stale and stack."""
    assert "t.closest('.wsteer-btn')" in UNIVERSE
    assert "el.addEventListener('click'" in UNIVERSE


def test_static_snapshot_offers_no_write_path() -> None:
    # the RENDERER block (braced), not setWinTab's proposal hook
    steer_tab = UNIVERSE[UNIVERSE.index("if (tab==='steer'){"):]
    assert "if (STATIC) return" in steer_tab[:200], "a static render must not offer Steer"
    assert "run <code>ent serve</code> to steer" in steer_tab[:400]
    # and the actions themselves refuse regardless of how they are reached
    assert UNIVERSE.count("if (STATIC) return;") >= 4


def test_gated_units_announce_the_approval_gate() -> None:
    assert "needs your sign-off — " in UNIVERSE
    assert "wappr-btn" in UNIVERSE and "wrej-btn" in UNIVERSE
