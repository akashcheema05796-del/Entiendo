"""Dynamic clock-dependency detector — execute under shifted clocks and diff.

The confirming instrument: for each unit with tier-0 smoke fixtures (captured
I/O), run the entrypoint at the current time as baseline, then re-run under
each shifted clock (`time-machine`); any output delta ⇒ `time_pure: false`
with the failing shift(s) as evidence. This catches what static analysis
cannot afford to: the seasonal `month == 12` branch that passes today.

Limits, stated in the report rather than papered over:
  - needs `time-machine` (optional extra `.[detect]`) — absent ⇒ skipped;
  - C extensions and subprocesses bypass time-machine's patching ⇒ such
    units are `time_check: incomplete` (escalation path: libfaketime via
    LD_PRELOAD — documented, deliberately not implemented);
  - only fixture-covered branches are observed (the usual dynamic caveat).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# The shift set: each is (label, aware-datetime factory). Chosen to trip the
# classic failure families — tomorrow, a season away, a year away, a DST
# boundary, Feb 29, and a +14h timezone flip.
SHIFTS: list[tuple[str, Any]] = [
    ("+1 day", lambda now: now + _dt.timedelta(days=1)),
    ("+180 days", lambda now: now + _dt.timedelta(days=180)),
    ("+1 year", lambda now: now + _dt.timedelta(days=365)),
    ("DST boundary (2026-03-08 01:59 America/Chicago)",
     lambda now: _dt.datetime(2026, 3, 8, 1, 59, tzinfo=ZoneInfo("America/Chicago"))),
    ("Feb 29 (2028-02-29)",
     lambda now: _dt.datetime(2028, 2, 29, 12, 0, tzinfo=ZoneInfo("UTC"))),
    ("TZ flip UTC → Pacific/Kiritimati",
     lambda now: now.astimezone(ZoneInfo("Pacific/Kiritimati"))),
]

# A seasonal branch (`month == 12`) is only exposed if some shift LANDS in
# that month — fixed offsets from an arbitrary "today" cannot guarantee it,
# so sweep a full year in ~monthly steps. This is what catches the branch
# that passes every test run until December.
SHIFTS += [(f"month sweep +{k}×30 days",
            (lambda k: lambda now: now + _dt.timedelta(days=30 * k))(k))
           for k in range(1, 13)]


def available() -> bool:
    try:
        import time_machine  # noqa: F401
        return True
    except ImportError:
        return False


def _rows_for(node: Any, root: Path) -> list[dict]:
    from ..evals.runner import load_rows
    rows: list[dict] = []
    for entry in (node.raw.get("evals", {}) or {}).get("tier0", []) or []:
        fixture = entry.get("fixture") if isinstance(entry, dict) else None
        if fixture and (root / fixture).exists():
            rows.extend(load_rows(root / fixture))
    return rows


def _outputs(node: Any, root: Path, rows: list[dict]) -> list[Any]:
    from ..evals.entrypoint import resolve_entrypoint
    from ..evals.runner import _invoker
    from .. import testing
    invoke = _invoker(node, root, resolve_entrypoint(node, root))
    outs: list[Any] = []
    for row in rows:
        with testing.stub(node, row):
            outs.append(invoke(row))
    return outs


def probe_unit(node: Any, root: Path) -> dict:
    """{time_pure, grade, findings, time_check} for one unit — or a skip note."""
    if not available():
        return {"time_check": "skipped", "note": "time-machine not installed "
                "(pip install 'entiendo[detect]')"}
    rows = _rows_for(node, root)
    if not rows:
        return {"time_check": "skipped", "note": "no smoke fixtures — nothing "
                "to replay under a shifted clock"}

    import time_machine

    try:
        baseline = _outputs(node, root, rows)
    except Exception as exc:
        return {"time_check": "incomplete",
                "note": f"baseline execution failed: {type(exc).__name__}: {exc}"}

    failing: list[str] = []
    incomplete: list[str] = []
    now = _dt.datetime.now(_dt.timezone.utc)
    for label, at in SHIFTS:
        try:
            with time_machine.travel(at(now), tick=False):
                shifted = _outputs(node, root, rows)
        except Exception as exc:
            incomplete.append(f"{label}: execution failed under shift "
                              f"({type(exc).__name__}) — possibly a C-extension "
                              "or subprocess time-machine cannot intercept")
            continue
        if shifted != baseline:
            deltas = [rows[i].get("name", f"row{i}")
                      for i in range(len(rows)) if shifted[i] != baseline[i]]
            failing.append(f"{label}: output changed for {', '.join(deltas)}")

    return {
        "time_pure": not failing,
        "grade": "dynamic",
        "findings": failing,
        "time_check": "incomplete" if incomplete else "complete",
        **({"incomplete": incomplete} if incomplete else {}),
    }
