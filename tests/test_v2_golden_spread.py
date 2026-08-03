"""V2 — golden-set spread + significance proof (PLAN_v5).

A benchmark everything passes at 1.0000 is not a benchmark. Per the V0 audit the
trivial score was metric saturation (greenfield ndcg@5), NOT a scoring bug — the
metric compares output to `row.expect`. This phase gives refundly.parse_email a
golden set that lands mid-band (0.78, not 1.0) and proves tier1 discriminates:
a real regression goes REGRESSED, a cosmetic change stays WITHIN_BAND.

Scoring unit tests lock the (c) bug-class (output-vs-self) out permanently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.evals.metrics import exact_match, f1, get_metric  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
GOLDEN = REFUNDLY / "evals" / "refundly.parse_email" / "golden_v3.jsonl"


# --------------------------------------------------------------------------- #
# scoring unit tests — hand-computed values (locks bug-class (c) out)
# --------------------------------------------------------------------------- #

def test_exact_match_hand_computed() -> None:
    assert exact_match({"orderId": "A1", "reason": "x"}, {"orderId": "A1", "reason": "x"}) == 1.0
    assert exact_match({"orderId": None, "reason": "x"}, {"orderId": "B1", "reason": "x"}) == 0.0
    # a differing reason also misses — it is a full-output compare, not a field
    assert exact_match({"orderId": "A1", "reason": "y"}, {"orderId": "A1", "reason": "x"}) == 0.0


def test_f1_hand_computed() -> None:
    # actual {a,b,c} vs expected {b,c,d}: tp=2, p=2/3, r=2/3, f1=2/3
    assert abs(f1({"items": ["a", "b", "c"]}, {"items": ["b", "c", "d"]}) - (2 / 3)) < 1e-9
    assert f1({"items": []}, {"items": []}) == 1.0
    assert f1({"items": ["a"]}, {"items": ["b"]}) == 0.0


def test_metric_compares_to_expected_not_self() -> None:
    # the (c) bug would be metric(out, out)==1 always; prove it compares to expect
    metric = get_metric("exact_match")
    out = {"orderId": "A1", "reason": "x"}
    assert metric(out, {"orderId": "Z9", "reason": "x"}) == 0.0   # NOT output-vs-self


# --------------------------------------------------------------------------- #
# the refundly golden set is a real (non-saturated) benchmark
# --------------------------------------------------------------------------- #

def _rows() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]


def _parse():
    sys.path.insert(0, str(REFUNDLY / "src" / "parse_email"))
    import importlib
    import parser as _p  # noqa
    importlib.reload(_p)
    return _p.parse


def test_golden_baseline_lands_in_band_not_saturated() -> None:
    parse = _parse()
    scores = [exact_match(parse(r["input"]), r["expect"]) for r in _rows()]
    mean = sum(scores) / len(scores)
    assert 0.75 <= mean <= 0.92, mean          # a discriminating baseline, not 1.0
    assert 0.0 in scores and 1.0 in scores     # genuinely mixed difficulty


def test_golden_rows_are_unblessed() -> None:
    # V2 authors rows; the human blesses in V3. Rows must not self-bless.
    node = find_node(REFUNDLY, "refundly.parse_email")
    golden = next(e for e in node.raw["evals"]["tier1"] if e["type"] == "golden")
    assert golden["humanBlessed"] is False
    assert 0.75 <= golden["baseline"] <= 0.92


# --------------------------------------------------------------------------- #
# significance harness: regression → red, noise → within band
# --------------------------------------------------------------------------- #

def test_real_regression_goes_red() -> None:
    node = find_node(REFUNDLY, "refundly.parse_email")

    def variant_R(req):
        # a real behavioral regression: also drop the uppercase 'ORDER' case,
        # so the score falls well below baseline - significance
        import re
        body = req.get("email", "")
        m = re.search(r"\border\s+(\w+)", body)   # case-SENSITIVE now (worse)
        return {"orderId": m.group(1) if m else None, "reason": req.get("reason", "unspecified")}

    result = run_tier1(node, REFUNDLY, entrypoint=variant_R)
    assert result.verdict == "REGRESSED"
    assert result.stats["delta"] < 0
    # per-signal detail is preserved (no verdict collapse)
    assert "mean" in result.stats and "baseline" in result.stats and "spread" in result.stats


def test_noise_stays_within_band() -> None:
    node = find_node(REFUNDLY, "refundly.parse_email")

    def variant_N(req):
        # a cosmetic change — identical behavior, reformatted
        import re
        text = req.get("email", "")
        match = re.search(r"order\s+(\w+)", text, flags=re.I)
        order_id = match.group(1) if match is not None else None
        return {"orderId": order_id, "reason": req.get("reason", "unspecified")}

    result = run_tier1(node, REFUNDLY, entrypoint=variant_N)
    assert result.verdict == "WITHIN_BAND"
    assert abs(result.stats["delta"]) <= 0.05
