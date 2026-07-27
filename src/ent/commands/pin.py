"""`ent pin` — pin a fingerprint dimension (v3 Phase E, SPEC §5.4).

    ent pin <unit> model=<id>

Writes the pin into the unit's manifest (comment-preserving), then records the
new fingerprint to history so the change is visible on the Timeline. Pinning the
old value back restores the fingerprint.

Exit codes: 0 pinned · 1 usage/target error · 2 manifests invalid
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import gitinfo, history
from ..manifest import find_node
from ..validation import validate_root
from ..version import compute_version, pin_model


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "pin",
        help="[L3] pin a fingerprint dimension (e.g. model) on a unit",
        description="Pin a unit's model dimension: `ent pin <unit> model=<id>`. "
                    "The fingerprint moves and is recorded on the Timeline.",
    )
    p.add_argument("unit", help="unit id, e.g. retrieval.chunk_ranker")
    p.add_argument("assignment", help="dimension assignment, currently only model=<id>")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if "=" not in args.assignment:
        print("ent pin: expected an assignment like model=<id>")
        return 1
    dim, value = args.assignment.split("=", 1)
    if dim != "model":
        print(f"ent pin: only 'model' is pinnable today, got '{dim}'")
        return 1

    report = validate_root(root)
    if not report.ok:
        print("ent pin: manifests are invalid — run `ent validate` first.")
        return 2

    node = find_node(root, args.unit)
    if node is None:
        print(f"ent pin: no unit '{args.unit}'")
        return 1

    prev = pin_model(node.path, value)
    # re-read the node so the new model is reflected, then record the fingerprint
    node = find_node(root, args.unit)
    version = compute_version(node, root)
    event = history.append_version(root, node.id, version,
                                   commit=gitinfo.short_commit(root), ts=gitinfo.now_iso())

    print(f"  pinned {args.unit} model: {prev or '—'} → {value}")
    print(f"  fingerprint {'moved to ' + version['composite'] if event else 'unchanged'}"
          f"{'  (recorded on Timeline)' if event else ''}")
    return 0
