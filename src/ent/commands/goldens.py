"""`ent goldens` — the repo-wide golden integrity manifest (hardening Phase 1).

  ent goldens verify [--require-lock] [--quiet]   exit 1 on any mismatch
  ent goldens bless                                regenerate entiendo/goldens.lock

`bless` here pins FILE INTEGRITY (which bytes are ground truth); the per-dataset
`ent bless` signs MEANING (a human vouches for expected values). Both, together:
a golden can neither change silently nor gate without a human signature.

Refuses to bless under CI (`ENTIENDO_CI=1` or `CI=1`) — the lock must change in
a PR a human reviews, never inside the pipeline that enforces it.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .. import integrity


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "goldens",
        help="[trust] verify or (re)pin the repo-wide golden hash manifest",
        description="Repo-wide golden integrity: entiendo/goldens.lock.",
    )
    p.add_argument("action", choices=["verify", "bless"])
    p.add_argument("--require-lock", action="store_true",
                   help="verify: fail when goldens exist but no lock does")
    p.add_argument("--quiet", action="store_true", help="verify: no output on success")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    if args.action == "verify":
        try:
            status = integrity.verify_manifest(root, require_lock=args.require_lock)
        except integrity.GoldenTamperError as exc:
            print(f"ent goldens verify: TAMPER — {exc}")
            return 1
        if not args.quiet:
            print(f"✓ {status}")
        return 0

    # bless — never from CI: the lock changes through PR review, not pipelines.
    if os.environ.get("ENTIENDO_CI") == "1" or os.environ.get("CI") == "1":
        print("ent goldens bless: refusing under CI — the lock is ground truth "
              "and must change in a reviewed PR, never inside the pipeline "
              "that enforces it.")
        return 3

    files = integrity.golden_files(root)
    path = integrity.write_lock(root)
    print("⚠  You are re-pinning GROUND TRUTH.")
    print(f"   {len(files)} golden file(s) hashed into {path.relative_to(root)}.")
    print("   This diff must go through PR review — a lock change without a "
          "matching golden change (or vice versa) is exactly what reviewers "
          "should reject.")
    return 0
