"""`ent snapshot` — L3. Record node versions + eval verdicts to history.

Computes each node's composite version and tier0 verdict and appends them to the
append-only history log (version events only when the composite changed). Run it
per commit so the timeline lens shows what changed, when.

Exit codes:
  0  snapshot recorded
  2  environment problem, or manifests invalid (run `ent validate`)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import gitinfo, history
from ..evals.runner import run_tier0
from ..manifest import discover, load, Node
from ..validation import validate_root
from ..version import compute_version


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "snapshot",
        help="[L3] record node versions + eval verdicts to history",
        description="Append current versions and tier0 verdicts to the history log.",
    )
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    try:
        report = validate_root(root)
        if not report.ok:
            print("ent snapshot: manifests are invalid — run `ent validate` first.")
            return 2
        nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    except ModuleNotFoundError as exc:
        print(f"ent snapshot: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    commit = gitinfo.short_commit(root)
    ts = gitinfo.now_iso()

    changed = 0
    for node in sorted(nodes, key=lambda n: n.id):
        version = compute_version(node, root)
        event = history.append_version(root, node.id, version, commit=commit, ts=ts)
        result = run_tier0(node, root)
        history.append_eval(root, node.id, result.verdict, 0, commit=commit, ts=ts)
        mark = "▲" if event else " "
        if event:
            changed += 1
        print(f"  {mark} {node.id:26} {version['composite']}  {result.verdict}")

    print()
    print(f"✓ snapshot recorded for {len(nodes)} node(s), "
          f"{changed} version change(s)" + (f" @ {commit}" if commit else ""))
    return 0
