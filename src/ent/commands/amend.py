"""`ent amend` — turn sideEffects contradictions into acceptable amendments.

  ent amend               list units whose `sideEffects: none` contradicts
                          effect-implying constructs in their claimed files
  ent amend --accept <id> apply ONE unit's amendment (none → external)

astrobee gap 5: the extractor flagged ~20 informational notes (scripts using
subprocess / network clients while their manifests declare `sideEffects:
none`) with no workflow to resolve them — hints that scroll away. This makes
each contradiction a staged, reviewable amendment, accepted one unit at a
time like retrofit proposals: the human blesses the contract change, the
tool only does the mechanical edit.

Only effect-implying patterns count (subprocess, requests, httpx, urllib —
and their JS counterparts child_process / network-client). Dynamic-import
and getattr dispatch are dependency-visibility notes, not effects; they stay
where they are.

Exit codes: 0 ok · 2 nothing to do / not found
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

# The subset of the extractor's blind-spot patterns that implies an EFFECT
# (the rest are visibility notes). Maps pattern name → the honest declaration.
_EFFECT_PATTERNS = {
    "subprocess": "external",
    "requests": "external",
    "httpx": "external",
    "urllib": "external",
    "child_process": "external",
    "network-client": "external",
}


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "amend",
        help="stage sideEffects amendments where declarations contradict the code",
        description="List (and one-at-a-time accept) sideEffects amendments for units "
                    "whose 'none' declaration contradicts effect-implying constructs.",
    )
    p.add_argument("root", nargs="?", default=".", help="project root (default: .)")
    p.add_argument("--accept", metavar="ID", help="apply one unit's staged amendment")
    p.set_defaults(handler=_run)


def find_amendments(root: Path) -> list[dict[str, Any]]:
    """Units declaring `sideEffects: none` whose claimed files hit an
    effect-implying pattern. Evidence included — never a bare claim."""
    from ..extractor import _dynamic_dep_warnings
    from ..manifest import Node, discover, load

    nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    declared_none = {n.id: n for n in nodes
                     if (n.raw.get("contract", {}) or {}).get("sideEffects") == "none"}
    evidence: dict[str, list[dict[str, str]]] = {}
    for w in _dynamic_dep_warnings(list(declared_none.values()), root):
        if w["pattern"] in _EFFECT_PATTERNS:
            evidence.setdefault(w["node"], []).append(w)

    out: list[dict[str, Any]] = []
    for node_id in sorted(evidence):
        out.append({
            "node": node_id,
            "current": "none",
            "proposed": "external",
            "evidence": evidence[node_id],
            "manifest": str(declared_none[node_id].path),
        })
    return out


def apply_amendment(root: Path, node_id: str) -> Path | None:
    """Flip one unit's `sideEffects: none` → `external` in place.

    A minimal text edit (never a YAML re-dump) so hand-written comments and
    formatting in the manifest survive. Returns the manifest path, or None
    if the unit has no staged amendment.
    """
    staged = {a["node"]: a for a in find_amendments(root)}
    amendment = staged.get(node_id)
    if amendment is None:
        return None
    path = Path(amendment["manifest"])
    text = path.read_text()
    needle = "sideEffects: none"
    if text.count(needle) != 1:            # ambiguous manifest — refuse to guess
        return None
    path.write_text(text.replace(needle, "sideEffects: external", 1))
    return path


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.accept:
        path = apply_amendment(root, args.accept)
        if path is None:
            print(f"ent amend: no staged amendment for '{args.accept}'")
            return 2
        print(f"✓ {args.accept}: sideEffects none → external ({path.relative_to(root)})")
        print("  re-run `ent extract` to refresh the map; the composite fingerprint moves")
        return 0

    amendments = find_amendments(root)
    if not amendments:
        print("ent amend: no contradictions — every sideEffects: none unit is clean "
              "under the static pass")
        return 0
    print(f"ent amend — {len(amendments)} unit(s) whose declaration contradicts the code\n")
    for a in amendments:
        print(f"  {a['node']}: sideEffects {a['current']} → {a['proposed']}")
        for ev in a["evidence"][:4]:
            print(f"      {ev['file']}: {ev['pattern']}")
        extra = len(a["evidence"]) - 4
        if extra > 0:
            print(f"      … and {extra} more file(s)")
    print("\n  accept one at a time: `ent amend . --accept <id>` — a contract change "
          "is a human decision, the tool only does the edit")
    return 0
