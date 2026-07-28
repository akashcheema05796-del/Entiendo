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
    html = _html()
    assert "trajectory RED" in html and "failedRule" in html     # the violated rule in the dossier


def test_dossier_reads_logic_first() -> None:
    html = _html()
    # description ("What it does") appears before Contract; interior before contract.
    assert html.index(">What it does</h3>") < html.index(">Contract</h3>")
    assert html.index("interiorSection(u)") < html.index(">Contract</h3>")


def test_interior_section_shows_process_and_maxsteps() -> None:
    html = _html()
    assert "function interiorSection" in html
    assert "u.interior.process" in html and "maxSteps" in html
