"""pytest-collection extractor (Phase 4, method 'collect').

Driven as: `pytest --collect-only -p ent.extract.collect_plugin <path>`
with `ENT_EXTRACT_OUT=<file>`. Collection resolves what the AST pass cannot
afford to — computed parametrize lists, fixture params, module/class-level
pytestmark — because pytest has already evaluated `callspec.params`.

Only JSON-representable param values are serialized; anything else becomes a
counted `not_extractable: needs_harness` entry, never a lossy repr. A test
with no callspec (plain function, likely fixture-driven I/O) is also flagged
needs_harness — collected, not extracted, visible in the coverage line.

SECURITY: collection executes module IMPORT (not test bodies). For untrusted
repos run this inside the eval sandbox, never on the host.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _jsonable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def pytest_collection_finish(session) -> None:  # pragma: no cover - runs inside pytest
    out_path = os.environ.get("ENT_EXTRACT_OUT")
    if not out_path:
        return
    cases: list[dict[str, Any]] = []
    for item in session.items:
        marks = sorted({m.name for m in item.iter_markers()})
        callspec = getattr(item, "callspec", None)
        entry: dict[str, Any] = {
            "source_test": item.nodeid,
            "case_id": item.name,
            "marks": marks,
            "extraction_method": "collect",
        }
        if callspec is None:
            entry.update({"not_extractable": "needs_harness",
                          "reason": "no parametrization — fixture/manual I/O"})
        else:
            params = dict(callspec.params)
            bad = sorted(k for k, v in params.items() if not _jsonable(v))
            if bad:
                entry.update({"not_extractable": "needs_harness",
                              "reason": f"non-serializable param(s): {', '.join(bad)}"})
            else:
                entry.update({"inputs": params,
                              "expected": params.pop("expected", None),
                              "confidence": "high"})
        cases.append(entry)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"collected": len(session.items), "cases": cases}, fh, indent=2)
