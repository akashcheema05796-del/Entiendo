"""Phase H4 acceptance (PLAN_v4.md) — interiors rendered (the gap that started v4).

The agentic interior is drawn (satellites tethered to their crossed edges, orbit
dashed when the registry is not enforced), the dossier's Interior section names
the violated rule on a trajectory-RED, trace playback descends into the interior
(satellites animate — verified in Chromium), and the dossier reads logic-first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.render import build_universe, build_view  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


def _html() -> str:
    return build_universe(None)


def test_interior_registry_flag_in_view() -> None:
    decide = next(n for n in build_view(REFUNDLY)["nodes"] if n["id"] == "refundly.decide")
    # decide's trajectory eval is registryOnly: true → the orbit renders solid
    assert decide["interior"]["registryOnly"] is True
    crosses = {t["crosses"] for t in decide["interior"]["tools"]}
    assert {"refundly.orders", "refundly.gateway"} <= crosses   # order_lookup + issue_refund tethers


def test_satellites_tethered_to_crossings() -> None:
    html = _html()
    assert "u.interior && u.interior.tools" in html
    assert "tl.crosses" in html and "byId[tl.crosses]" in html   # tether to the crossed unit
    assert "u.interior.registryOnly ? [] :" in html              # dashed orbit when not enforced


def test_trace_descends_into_interiors() -> None:
    html = _html()
    assert "descendIntoInteriors" in html and "satelliteLog" in html and "activeSat" in html
    # a failed hop still lights its tool (so the out-of-order call is visible)
    assert "_halted" in html


def test_red_trajectory_names_the_rule() -> None:
    """A broken tool ORDER must name the rule it broke, not just say RED."""
    html = _html()
    assert "tool order broke a rule" in html and "failedRule" in html


def test_unit_window_reads_logic_first() -> None:
    """Prose before mechanics: what the unit is FOR, and what it can do, come
    before its rules and edges. The unit window replaced the docked panel;
    the ordering rule survives it."""
    html = _html()
    inside = html.index("if (tab==='inside')")
    promises = html.index("if (tab==='promises')")
    assert inside < promises                       # 'inside' is the first tab
    assert html.index("n.description?`<div class=\"wprose\"") < promises
    assert html.index("winInterior(n)") < promises


def test_interior_shows_process_and_maxsteps() -> None:
    """An agentic unit's insides are its tools and how many steps it may take —
    shown in the same 'inside' tab as a plain unit's functions."""
    html = _html()
    assert "function winInterior" in html
    assert "n.interior.process" in html and "maxSteps" in html
