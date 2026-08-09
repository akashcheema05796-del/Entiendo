"""Phase H3 acceptance (PLAN_v4.md) — real lenses.

Structure tests over the emitted HTML + the view model (runtime playback/scrub
verified separately in Chromium): Trace playback, the Timeline scrubber over a
real commit axis, the cost overlay, per-edge Flow labels, and blast rank labels.
Plus the backend the lenses read: a commit axis and a replay endpoint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent import server  # noqa: E402
from ent.render import build_universe, build_view  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


def _html() -> str:
    return build_universe(None)


# --------------------------------------------------------------------------- #
# backend: the commit axis + replay endpoint the lenses read
# --------------------------------------------------------------------------- #

def test_commit_axis_in_view() -> None:
    view = build_view(REFUNDLY)
    commits = [c["commit"] for c in view["commits"]]
    assert commits == ["c1-init", "c2-model"]          # ordered, distinct


def test_decide_fingerprint_changes_across_commits() -> None:
    view = build_view(REFUNDLY)
    ticks = [e for e in view["timelines"]["refundly.decide"] if e["kind"] == "version"]
    assert len(ticks) == 2
    assert ticks[0]["composite"] != ticks[1]["composite"]   # scrubbing shows a real change
    assert ticks[1]["changed"] == ["model"]


def test_replay_endpoint() -> None:
    status, payload = server.handle_api(
        REFUNDLY, "POST", "/api/node/refundly.decide/replay",
        {"against": build_view(REFUNDLY)["timelines"]["refundly.decide"][0]["composite"]})
    assert status == 200
    assert payload["unit"] == "refundly.decide"
    assert "changedDimensions" in payload


def test_traces_are_playback_ready() -> None:
    view = build_view(REFUNDLY)
    assert len(view["traces"]) >= 3
    bad = next(t for t in view["traces"] if t["id"] == "req-bad-order")
    assert bad["hops"] and all("duration_ms" in h and "status" in h for h in bad["hops"])
    assert any(h["status"] == "error" for h in bad["hops"])   # a failed hop to halt the comet


# --------------------------------------------------------------------------- #
# frontend: each lens is a genuinely different view
# --------------------------------------------------------------------------- #

def test_trace_playback_present() -> None:
    html = _html()
    assert "renderTracePicker" in html and "playbackTrace" in html and "function drawComet" in html
    assert "status==='error'" in html                  # failed hop halts + pulses red
    assert "hopinfo" in html                            # per-hop latency + status annotation


def test_timeline_scrubber_present() -> None:
    html = _html()
    assert "renderScrubber" in html and 'id="scrub"' in html
    assert "tickAtCommit" in html and "view.commits" in html
    assert "winReplay" in html                        # tick action wired to replay


def test_cost_overlay_and_legend() -> None:
    html = _html()
    assert "budgetBurn" in html                         # measured/declared arc
    assert "speed/cost budget" in html                # the arc is explained in the legend


def test_flow_edge_labels() -> None:
    html = _html()
    assert "lens==='flow'" in html and "e.kinds" in html   # per-edge kind labels


def test_blast_rank_labels() -> None:
    html = _html()
    assert "blastCoupling" in html and "'rank '" in html
