"""`ent replay` — replay a unit against an old fingerprint (v3 Phase E, §5.4).

    ent replay <unit> --against <fingerprint>

Compares the golden metric now vs at an old fingerprint and attributes the delta
to the dimensions that changed (code / prompt / config / model). The old side
comes from the history store (git + recorded golden results).

Exit codes: 0 ok · 1 target/fingerprint error · 2 manifests invalid
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..replay import replay
from ..validation import validate_root


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "replay",
        help="[L3] replay a unit's golden fixtures against an old fingerprint",
        description="Side-by-side golden metric now vs at an old fingerprint, with "
                    "the delta attributed to the changed dimensions.",
    )
    p.add_argument("unit", help="unit id, e.g. retrieval.chunk_ranker")
    p.add_argument("--against", required=True, metavar="FINGERPRINT",
                   help="the old composite fingerprint (exact or unique prefix)")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = validate_root(root)
    if not report.ok:
        print("ent replay: manifests are invalid — run `ent validate` first.")
        return 2

    result = replay(root, args.unit, args.against)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if "error" not in result else 1

    if "error" in result:
        print(f"ent replay: {result['error']}")
        return 1

    old, cur = result["old"], result["current"]
    print(f"  replay {result['unit']}  (against {args.against})")
    print(f"    fingerprint   {old['composite']}  →  {cur['composite']}")
    print(f"    changed dims  {result['attribution']}")
    print(f"    {result['metric'] or 'metric'}: "
          f"{_fmt(old['score'])} (then, {old['scoreSource']})  →  {_fmt(cur['score'])} (now)")
    if result["delta"] is not None:
        print(f"    delta         {result['delta']:+}  → {result['verdict']} "
              f"(significance {result['significance']})")
    else:
        print(f"    delta         — ({result['verdict']}; a score is unavailable on one side)")
    return 0


def _fmt(x) -> str:
    return f"{x:.4f}" if isinstance(x, (int, float)) else "—"
