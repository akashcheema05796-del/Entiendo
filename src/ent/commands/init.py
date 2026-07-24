"""`ent init` — L0. Scaffold entiendo/ and (optionally) a first node manifest.

Idempotent and non-destructive: it creates what's missing and never overwrites a
file that already exists. Generated artifacts (graph.json / coverage.json) are
NOT written here — those come from `ent extract` (L1).

Usage:
  ent init                                  # scaffold entiendo/ only
  ent init --node-id retrieval.ranker --at src/retrieval
                                            # + a starter manifest at that module
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..manifest import MANIFEST_FILENAME

_ARTIFACT_README = """\
# `entiendo/` — generated artifacts

Everything here is **generated, never hand-edited** (SPEC.md §12).

| File / dir | Written by | Contents |
|---|---|---|
| `graph.json` | `ent extract` (L1) | Node topology + verified edges |
| `coverage.json` | `ent extract` (L1) | Claimed vs unclaimed files |
| `baselines/` | `ent eval` (L2/L3) | Eval baselines per node version |
| `history/` | history store (L3) | Append-only version + eval event log |

Never resolve a merge conflict inside graph.json / coverage.json by hand —
re-run the extractor instead.
"""


def _starter_manifest(node_id: str) -> str:
    group = node_id.split(".")[0] if "." in node_id else node_id
    return f"""\
apiVersion: entiendo/v1
kind: Node

id: {node_id}
name: {node_id}
nodeKind: compute                   # compute | state | schema | config | external | pipeline
group: {group}
owner: TODO                         # human accountable, not the AI
status: active

# What this node owns. Every claimed file must exist (drives coverage).
claims:
  - TODO/path/to/source.py

# The contract: what "correct" means for THIS node alone.
contract:
  invariants: []
  sideEffects: none                 # none | writes | external | irreversible

# Declared edges. The extractor VERIFIES these against reality (L1).
dependencies:
  calls:  []
  reads:  []
  writes: []
  config: []

# No node without a tier-0 eval (Invariant 3).
evals:
  tier0:
    - type: schema_validation
    - type: invariant_check

observability:
  spanName: {node_id}

approval:
  required: false
"""


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "init",
        help="[L0] scaffold entiendo/ + a first node manifest",
        description="Scaffold the entiendo/ layout and, optionally, a first manifest.",
    )
    p.add_argument(
        "--path",
        default=".",
        help="project root to initialise (default: current directory)",
    )
    p.add_argument(
        "--node-id",
        help="id for a starter manifest, e.g. retrieval.chunk_ranker",
    )
    p.add_argument(
        "--at",
        help="module directory to write the starter manifest into (with --node-id)",
    )
    p.set_defaults(handler=_run)


def _write_if_absent(path: Path, content: str, created: list[str], skipped: list[str]) -> None:
    if path.exists():
        skipped.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    created.append(str(path))


def _run(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    created: list[str] = []
    skipped: list[str] = []

    # --- artifact scaffold ---
    entiendo = root / "entiendo"
    for sub in ("baselines", "history"):
        (entiendo / sub).mkdir(parents=True, exist_ok=True)
    _write_if_absent(entiendo / "README.md", _ARTIFACT_README, created, skipped)
    _write_if_absent(entiendo / "baselines" / ".gitkeep", "", created, skipped)
    _write_if_absent(entiendo / "history" / ".gitkeep", "", created, skipped)

    # --- optional starter manifest ---
    if args.node_id and args.at:
        target = root / args.at / MANIFEST_FILENAME
        _write_if_absent(target, _starter_manifest(args.node_id), created, skipped)
    elif args.node_id or args.at:
        print("ent init: --node-id and --at must be given together; skipping manifest.\n")

    # --- report ---
    for c in created:
        print(f"  created  {c}")
    for s in skipped:
        print(f"  exists   {s}")

    print()
    print(f"✓ initialised entiendo/ at {root}")
    if not (args.node_id and args.at):
        print("  next: `ent init --node-id <id> --at <module-dir>` to add a node,")
        print("        then `ent validate` to check it.")
    else:
        print("  next: fill in the TODOs, then `ent validate`.")
    return 0
