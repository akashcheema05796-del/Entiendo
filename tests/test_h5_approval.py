"""Phase H5 acceptance (PLAN_v4.md) — diff-first steer + approve (the v4 demo).

The final phase closes the loop the operator actually runs: steer a gated unit,
the workload edits and the change is held back as a *proposal*, and the dossier
shows the diff + behaviour delta + verdict *together* so a human approves the
change they can see — not a summary of it. Approve applies the stored diff;
Reject discards it and leaves the working tree untouched.

Frontend structure is asserted over the emitted HTML (the live click-through was
verified in Chromium); the proposal *lifecycle* (propose → hold → approve/reject)
is covered by the backend tests in test_h0.py, so this file does not repeat it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.render import build_universe  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _html() -> str:
    return build_universe(None)


# --------------------------------------------------------------------------- #
# the approval surface: proposals section, Approve + Reject, both wired
# --------------------------------------------------------------------------- #

def test_the_gate_offers_both_actions() -> None:
    """The gate lives in the unit window's steer tab now — one surface per unit,
    so two open units cannot approve each other's proposal."""
    html = _html()
    assert 'class="wsteer-props"' in html            # where an open proposal renders
    assert ">Approve<" in html and ">Reject<" in html
    assert "wappr-btn" in html and "wrej-btn" in html
    assert "async function winSettle" in html


def test_gated_unit_loads_its_open_proposal() -> None:
    html = _html()
    # opening the steer tab fetches the open proposals for THAT unit (H5)
    assert "async function winProposals" in html
    assert "n.approvalRequired" in html and "winProposals(id, w.el)" in html
    assert "/api/proposals" in html


def test_approve_reject_call_the_real_endpoints() -> None:
    html = _html()
    assert "/api/proposals/${pid}/${action}" in html      # approve | reject
    assert "'approve'" in html and "'reject'" in html


# --------------------------------------------------------------------------- #
# diff-first: the human approves the change they can SEE (diff + delta + verdict)
# --------------------------------------------------------------------------- #

def test_proposal_card_is_diff_first() -> None:
    html = _html()
    assert "function proposalCard" in html
    # the card shows the behaviour delta and the verdict alongside the diff
    assert "behaviourDelta" in html and "verdictAfter" in html
    assert "p.unifiedDiffs?renderDiffs(p.unifiedDiffs)" in html   # the diff is rendered inline


def test_diffs_render_per_file_in_monospace() -> None:
    html = _html()
    assert "function renderDiffs" in html
    # each changed file collapses under its own summary, rendered in the mono face
    assert "<details" in html and "var(--font-mono)" in html
    # +/- lines are coloured with the signal palette
    assert "var(--signal-green)" in html and "var(--signal-red)" in html


# --------------------------------------------------------------------------- #
# the map itself signals a waiting gate — the pulsing gold approval ring
# --------------------------------------------------------------------------- #

def test_waiting_gate_pulses_gold_on_the_map() -> None:
    html = _html()
    assert "pendingApproval" in html
    # a unit with a proposal waiting draws a full pulsing ring; else a small arc
    assert "pendingApproval.has(u.id)" in html
    assert "waiting?0:-0.9" in html and "waiting?Math.PI*2:-0.1" in html
    assert "--annotation" in html                    # the gold plate colour


def test_static_snapshot_disables_the_gate_actions() -> None:
    html = _html()
    # in a static render there is no server to approve against — the steer tab
    # refuses to draw any control, and every action returns early
    assert "run <code>ent serve</code> to steer" in html
    assert html.count("if (STATIC) return;") >= 5
