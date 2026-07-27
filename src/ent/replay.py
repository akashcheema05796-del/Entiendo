"""Fingerprint replay (v3 Phase E, SPEC §5.4) — the Day-30 payoff.

"It scored 0.79 today; it was 0.86 three weeks ago — what moved?" A unit's
fingerprint is composite (code · prompt · config · model), and the history store
records every fingerprint a unit has had, per dimension. Replay compares an old
fingerprint against the current one:

  - **which dimensions changed** — the attribution (code? prompt? config? model?);
  - **the golden metric then vs now** — the old side from the recorded golden run
    in the history store, the current side re-run live, with a significance
    verdict on the delta.

When only non-code dimensions moved (e.g. a model pin) the runnable artifacts are
identical, so "then" is a faithful re-run of the current code; when code moved,
the old score comes from the golden result recorded at that fingerprint. Either
way the delta is attributed to specific dimensions — that is the payoff.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from . import history, verdicts
from .manifest import find_node
from .version import VERSION_DIMENSIONS, compute_version


def resolve_fingerprint(root: Path, node_id: str, against: str) -> dict[str, Any] | None:
    """Find a recorded fingerprint for `node_id` whose composite matches `against`
    (exact or unique prefix). Returns {composite, version, commit} or None."""
    matches = []
    for e in history.read_events(root):
        if e.get("kind") == "version" and e.get("nodeId") == node_id:
            comp = e.get("composite") or ""
            if comp == against or comp.startswith(against):
                matches.append(e)
    if not matches:
        return None
    e = matches[-1]  # most recent matching fingerprint
    return {"composite": e.get("composite"), "version": e.get("version", {}), "commit": e.get("commit")}


def dimension_diff(old: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """The version dimensions (code/prompt/config/model) that differ."""
    return [d for d in VERSION_DIMENSIONS if old.get(d) != current.get(d)]


def _recorded_score(root: Path, node_id: str, composite: str) -> float | None:
    """The mean golden metric recorded at a fingerprint, from history/evals.jsonl."""
    path = Path(root) / "entiendo" / "history" / "evals.jsonl"
    if not path.exists():
        return None
    found = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("nodeId") == node_id and row.get("compositeVersion") == composite and "mean" in row:
            found = row["mean"]
    return found


def _significance(node: Any) -> float:
    for entry in node.raw.get("evals", {}).get("tier1", []) or []:
        if entry.get("type") == "golden" and entry.get("significance") is not None:
            return float(entry["significance"])
    return 0.03


def _verdict(delta: float | None, sig: float) -> str:
    if delta is None:
        return "UNKNOWN"
    if abs(delta) <= sig:
        return verdicts.WITHIN_BAND
    return verdicts.IMPROVED if delta > 0 else verdicts.REGRESSED


def replay(root: Path, node_id: str, against: str,
           *, entrypoint: Callable[..., Any] | None = None,
           run_tier1: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Replay a unit's golden fixtures at `against` (an old fingerprint) vs current.

    `run_tier1` is injectable for testing; by default the real golden runner.
    Returns a structured, side-by-side result with the dimension attribution.
    """
    root = Path(root)
    node = find_node(root, node_id)
    if node is None:
        return {"error": f"no unit '{node_id}'"}

    old = resolve_fingerprint(root, node_id, against)
    if old is None:
        return {"error": f"no recorded fingerprint matching '{against}' for {node_id} "
                         f"— run `ent snapshot` to record fingerprints"}

    current = compute_version(node, root)
    changed = dimension_diff(old["version"], current)

    if run_tier1 is None:
        from .evals.runner import run_tier1 as _rt1
        run_tier1 = _rt1

    cur_eval = run_tier1(node, root, entrypoint=entrypoint)
    cur_score = cur_eval.stats.get("mean") if getattr(cur_eval, "stats", None) else None

    # The old score: identical runnable artifacts (only non-code dims moved) → a
    # faithful re-run; otherwise the golden result recorded at that fingerprint.
    artifacts_same = all(old["version"].get(d) == current.get(d) for d in ("code", "prompt", "config"))
    if artifacts_same:
        old_score, old_source = cur_score, "same artifacts (re-run)"
    else:
        old_score = _recorded_score(root, node_id, old["composite"])
        old_source = "history (recorded golden)" if old_score is not None else "unavailable"

    delta = (cur_score - old_score) if (cur_score is not None and old_score is not None) else None
    sig = _significance(node)

    return {
        "unit": node_id,
        "against": against,
        "changedDimensions": changed,
        "attribution": (", ".join(changed) if changed else "no change"),
        "old": {"composite": old["composite"], "version": old["version"],
                "commit": old.get("commit"), "score": old_score, "scoreSource": old_source},
        "current": {"composite": current["composite"], "version": current, "score": cur_score},
        "metric": (cur_eval.stats.get("metric") if getattr(cur_eval, "stats", None) else None),
        "delta": round(delta, 4) if delta is not None else None,
        "significance": sig,
        "verdict": _verdict(delta, sig),
    }
