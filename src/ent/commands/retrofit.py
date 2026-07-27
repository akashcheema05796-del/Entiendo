"""`ent retrofit` — propose manifests for an existing repo (SPEC §12 v2).

  ent retrofit <root>                  analyse + write proposals to entiendo/proposals/
  ent retrofit <root> --accept <id>    promote one proposal into place (node-by-node)

A semi-automated migration: it infers boundaries and stages proposals — each
phrased as a task and marked boundary-uncertain until a human supplies a
fixture -> expected verdict (the law). Accept ONE at a time; there is
deliberately no bulk accept — blessing a boundary you haven't reviewed is the
tautology this whole tool exists to prevent (§5.2).

Exit codes: 0 ok · 2 nothing to do / not found
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import retrofit


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "retrofit",
        help="[v2] propose unit manifests for an existing repo",
        description="Infer unit boundaries in an unmanaged repo and stage manifest proposals.",
    )
    p.add_argument("root", nargs="?", default=".", help="repo to retrofit (default: current directory)")
    p.add_argument("--accept", metavar="ID", help="promote one staged proposal into place (one at a time)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.accept:
        return _accept(root, args)
    return _propose(root)


def _propose(root: Path) -> int:
    try:
        proposals = retrofit.propose(root)
    except ModuleNotFoundError as exc:
        print(f"ent retrofit: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    if not proposals:
        print(f"ent retrofit: no source files found under {root}")
        return 2

    out = retrofit.write_proposals(root, proposals)
    cov = retrofit.coverage(root, proposals)

    for p in sorted(proposals, key=lambda p: p.node_id):
        deps = p.manifest["dependencies"]["calls"]
        print(f"  [{p.confidence:6}] {p.node_id:28} {p.manifest['nodeKind']:8} "
              f"{len(p.manifest['claims'])} file(s)"
              + (f"  → {', '.join(deps)}" if deps else ""))
        print(f"           task: {p.manifest['task']}")
        print(f"           ⚠ boundary-uncertain — needs a fixture → expected verdict before accept")

    print()
    print(f"✓ {cov['nodes']} unit(s) proposed, {int(cov['coverage']*100)}% of "
          f"{cov['total']} source files claimed")
    print(f"  written to {out.relative_to(root)}/ — review, then `ent retrofit . --accept <id>`")
    print("  expect to correct many guesses: retrofit infers boundaries nobody declared.")
    return 0


def _accept(root: Path, args: argparse.Namespace) -> int:
    dest = retrofit.accept(root, args.accept)
    if dest is None:
        print(f"ent retrofit: no proposal for '{args.accept}'")
        return 2
    print(f"✓ accepted {args.accept} → {dest.relative_to(root)}")
    print("  next: give it a task + one fixture -> expected verdict, then `ent eval`.")
    return 0
