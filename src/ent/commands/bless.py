"""`ent bless <node>` — sign a golden dataset (Phase 7 §8).

Displays the dataset rows for human review, then writes a signature over the
dataset *content* (sha256) to entiendo/baselines/<node-id>.bless.json. At tier1
time the runner rehashes the dataset; if it changed since blessing, the blessing
is void and the run is advisory-only. Blessing content, not a filename, is what
stops an AI from editing its own golden rows into a pass.

Exit codes: 0 blessed · 2 no golden dataset / node not found
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import baselines, gitinfo
from ..evals.runner import load_rows
from ..manifest import find_node


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "bless",
        help="[golden] sign a unit's golden dataset for gating",
        description="Review and sign a golden dataset (humanBlessed).",
    )
    p.add_argument("node", metavar="unit", help="unit id, e.g. retrieval.chunk_ranker")
    p.add_argument("--by", default=None, help="who is blessing (default: $USER)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    import os

    root = Path(args.root).resolve()
    node = find_node(root, args.node)
    if node is None:
        print(f"ent bless: no unit with id '{args.node}' under {root}")
        return 2

    golden = next((e for e in node.raw.get("evals", {}).get("tier1", []) if e.get("type") == "golden"), None)
    if not golden or not golden.get("dataset"):
        print(f"ent bless: {args.node} has no golden dataset to bless")
        return 2

    dataset_rel = golden["dataset"]
    dataset_path = root / dataset_rel
    if not dataset_path.exists():
        print(f"ent bless: dataset '{dataset_rel}' not found")
        return 2

    rows = load_rows(dataset_path)
    print(f"Golden dataset for {args.node}: {dataset_rel} ({len(rows)} rows)\n")
    for i, row in enumerate(rows):
        print(f"  [{i}] {row.get('name', '')}: input={row.get('input')}  expect={row.get('expect')}")
    print()

    if not args.yes:
        answer = input("Bless these expected outputs? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("aborted — not blessed.")
            return 0

    blessed_by = args.by or os.environ.get("USER", "unknown")
    sha = baselines.dataset_sha256(dataset_path)
    baselines.write_bless(root, args.node, dataset_rel=dataset_rel, sha=sha,
                          rows=len(rows), blessed_by=blessed_by, blessed_at=gitinfo.now_iso())
    print(f"✓ blessed {args.node} — {len(rows)} rows, sha256 {sha[:12]}… by {blessed_by}")
    return 0
