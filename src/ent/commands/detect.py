"""`ent detect time [unit...]` — clock-dependency report (hardening Phase 3).

Static pass always (AST + transitive call graph); dynamic pass wherever the
unit has smoke fixtures and `time-machine` is installed (`.[detect]`). The
result is a component PROPERTY (`time_pure`), never a test failure — a unit
may legitimately read the clock; what matters is that the map says so.

Exit codes: 0 report produced · 2 no such unit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..detectors import time_dynamic, time_static
from ..manifest import Node, discover, load


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "detect",
        help="[quality] detect component properties (currently: time)",
        description="Component-property detectors. `ent detect time` reports time_pure.",
    )
    p.add_argument("property", choices=["time"])
    p.add_argument("units", nargs="*", help="unit ids (default: every unit)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    if args.units:
        missing = sorted(set(args.units) - {n.id for n in nodes})
        if missing:
            print(f"ent detect: no unit(s) {', '.join(missing)}")
            return 2
        selected = [n for n in nodes if n.id in set(args.units)]
    else:
        selected = nodes

    # static spans ALL units so cross-unit helpers propagate, then filters
    static = time_static.analyze_units(root, nodes)
    report: dict[str, dict] = {}
    for node in selected:
        s = static.get(node.id, {"time_pure": True, "findings": []})
        d = time_dynamic.probe_unit(node, root)
        ran_dynamic = "time_pure" in d
        merged = {
            "time_pure": s["time_pure"] and (d.get("time_pure", True)),
            "time_check": (d.get("time_check", "skipped")
                           if ran_dynamic else "static-only"),
            "static": {"time_pure": s["time_pure"], "findings": s["findings"]},
            "dynamic": d,
        }
        report[node.id] = merged

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    for unit in sorted(report):
        r = report[unit]
        mark = "✓" if r["time_pure"] else "✗"
        print(f"{mark} {unit}: time_pure={str(r['time_pure']).lower()} "
              f"({r['time_check']})")
        for line in r["static"]["findings"]:
            print(f"    static   {line}")
        for line in r["dynamic"].get("findings", []) or []:
            print(f"    dynamic  {line}")
        for line in r["dynamic"].get("incomplete", []) or []:
            print(f"    !        {line}")
        if note := r["dynamic"].get("note"):
            print(f"    ·        {note}")
    return 0
