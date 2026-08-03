"""`ent bless <node>` — sign a golden dataset (Phase 7 §8).

Displays the dataset rows for human review, then writes a signature over the
dataset *content* (sha256) to entiendo/baselines/<node-id>.bless.json. At tier1
time the runner rehashes the dataset; if it changed since blessing, the blessing
is void and the run is advisory-only. Blessing content, not a filename, is what
stops an AI from editing its own golden rows into a pass.

Blessing is a human gate (V3): it requires an interactive TTY (even with
`--yes`), and it records a real identity (`--as` → `entiendo/config.toml` →
`git config user.email`) — never `"unknown"`, and no env-var bypass.

Exit codes: 0 blessed / aborted · 2 no dataset / node / identity · 3 non-interactive
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import baselines, gitinfo
from ..evals.runner import load_rows
from ..identity import IdentityError, resolve_identity
from ..manifest import find_node


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "bless",
        help="[golden] sign a unit's golden dataset for gating",
        description="Review and sign a golden dataset (humanBlessed).",
    )
    p.add_argument("node", metavar="unit", help="unit id, e.g. retrieval.chunk_ranker")
    p.add_argument("--as", dest="as_", default=None, metavar="IDENTITY",
                   help="who is blessing (else entiendo/config.toml, else git user.email)")
    p.add_argument("--by", dest="as_", help=argparse.SUPPRESS)   # back-compat alias for --as
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt (still needs a TTY)")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    node = find_node(root, args.node)
    if node is None:
        print(f"ent bless: no unit with id '{args.node}' under {root}")
        return 2

    golden = next((e for e in node.raw.get("evals", {}).get("tier1", []) if e.get("type") == "golden"), None)
    if not golden or not golden.get("dataset"):
        print(f"ent bless: {args.node} has no golden dataset to bless")
        return 2

    # A human gate: blessing requires an interactive session — even with --yes,
    # and with no env-var escape hatch. CI cannot bless a baseline.
    if not sys.stdin.isatty():
        print("ent bless: Blessing requires an interactive session. Baselines are "
              "a human gate — they cannot be blessed from CI or a script.")
        return 3

    # A real identity, resolved before we ask — fail early if none.
    try:
        blessed_by = resolve_identity(root, explicit=args.as_)
    except IdentityError as exc:
        print(f"ent bless: {exc}")
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
    print(f"\nblessing as: {blessed_by}")

    if not args.yes:
        answer = input("Bless these expected outputs? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("aborted — not blessed.")
            return 0

    sha = baselines.dataset_sha256(dataset_path)
    baselines.write_bless(root, args.node, dataset_rel=dataset_rel, sha=sha,
                          rows=len(rows), blessed_by=blessed_by, blessed_at=gitinfo.now_iso())
    print(f"✓ blessed {args.node} — {len(rows)} rows, sha256 {sha[:12]}… by {blessed_by}")
    return 0
