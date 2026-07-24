"""Eval metrics for tier1 golden scoring.

A small registry keyed by metric name. `ndcg@k` is parsed for its k. Each metric
takes (actual_output, expected) and returns a score in [0, 1]. Kept pure and
deterministic so tier1's non-determinism comes only from the node, not the metric.
"""

from __future__ import annotations

import math
from typing import Any, Callable

Metric = Callable[[Any, Any], float]


def exact_match(actual: Any, expected: Any) -> float:
    """1.0 if the whole output equals expected, else 0.0."""
    return 1.0 if actual == expected else 0.0


def accuracy(actual: Any, expected: Any) -> float:
    """Label accuracy: compares actual['label'] to expected['label'] (or bare values)."""
    a = actual.get("label") if isinstance(actual, dict) else actual
    e = expected.get("label") if isinstance(expected, dict) else expected
    return 1.0 if a == e else 0.0


def ndcg_at_k(actual: Any, expected: Any, k: int) -> float:
    """Normalised DCG@k. actual = {'chunks': [{'id': ...}, ...]} ranked best-first;
    expected = {'top_ids': [...]} the set of relevant ids (binary relevance)."""
    ranked = [c.get("id") for c in (actual.get("chunks") or [])][:k]
    relevant = set(expected.get("top_ids") or [])
    if not relevant:
        return 1.0 if not ranked else 0.0
    dcg = sum((1.0 if rid in relevant else 0.0) / math.log2(i + 2) for i, rid in enumerate(ranked))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal > 0 else 0.0


def get_metric(name: str) -> Metric:
    """Resolve a metric by name. Supports 'ndcg@<k>', 'exact_match', 'accuracy'."""
    if name.startswith("ndcg@"):
        k = int(name.split("@", 1)[1])
        return lambda a, e: ndcg_at_k(a, e, k)
    table: dict[str, Metric] = {"exact_match": exact_match, "accuracy": accuracy}
    if name not in table:
        raise KeyError(f"unknown metric '{name}' (have: ndcg@k, {', '.join(table)})")
    return table[name]
