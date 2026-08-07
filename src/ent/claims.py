"""The single claims authority (PLAN_v6 1.4). One boundary check, used everywhere.

The claims boundary was enforced as string set-membership in three separate
flavours (V6_VERIFICATION V0.2) — none resolved symlinks, none proved the target
stays inside the repo. This module is the one implementation every write path
routes through:

  - the target is `os.path.realpath`'d and must satisfy
    `os.path.commonpath([target, repo_root]) == repo_root` (no `../` escapes,
    no symlink hops out of the tree);
  - each claim is realpath'd too — a claim that is itself a symlink pointing
    outside the repo claims nothing;
  - membership is decided on the resolved paths, then reported back as the
    canonical repo-relative posix path (what diffs/backups key on).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_GLOB_MAGIC = ("*", "?", "[")


def is_glob(claim: str) -> bool:
    return any(ch in claim for ch in _GLOB_MAGIC)


def expand_claims(root: Path, claims: Any) -> list[str]:
    """Claims, with glob patterns expanded to the files they match (v7).

    A monorepo unit can claim `src/agents/**/*.ts` instead of enumerating
    thousands of paths. Expansion is against the CURRENT tree — a glob claims
    exactly what exists when it is resolved, so a freshly created file is
    covered on the next resolution, and a glob never authorises anything the
    tree doesn't contain. Literal claims pass through untouched (missing
    literal files stay listed — downstream decides what missing means).
    Deterministic: sorted, de-duplicated, repo-relative posix.
    """
    root = Path(root)
    out: list[str] = []
    seen: set[str] = set()
    for claim in claims or []:
        if is_glob(str(claim)):
            matches = sorted(p for p in root.glob(str(claim)) if p.is_file())
            for m in matches:
                rel = m.relative_to(root).as_posix()
                if rel not in seen:
                    seen.add(rel); out.append(rel)
        else:
            rel = Path(str(claim)).as_posix()
            if rel not in seen:
                seen.add(rel); out.append(rel)
    return out


def _real(p: Path | str) -> str:
    return os.path.realpath(str(p))


def _inside(target_real: str, root_real: str) -> bool:
    try:
        return os.path.commonpath([target_real, root_real]) == root_real
    except ValueError:                     # different drives (Windows) etc.
        return False


def resolved_claims(root: Path, node: Any) -> dict[str, str]:
    """realpath → canonical repo-relative posix path, for claims inside the repo.

    A claim whose realpath escapes the repo (symlink out) is dropped — it can
    never authorise a write.
    """
    root_real = _real(root)
    out: dict[str, str] = {}
    for claim in expand_claims(root, getattr(node, "claims", []) or []):
        claim_real = _real(Path(root) / claim)
        if _inside(claim_real, root_real):
            out[claim_real] = Path(claim).as_posix()
    return out


def claimed_rel(root: Path, node: Any, target: str | Path) -> str | None:
    """The canonical claimed relative path for `target`, or None if out of bounds.

    `target` may be relative (to the repo root) or absolute; it need not exist
    yet (realpath resolves the existing prefix). Returns the claim's canonical
    repo-relative posix path iff the resolved target stays inside the repo AND
    matches a resolved claim.
    """
    root_real = _real(root)
    t = Path(target)
    target_real = _real(t if t.is_absolute() else Path(root) / t)
    if not _inside(target_real, root_real):
        return None
    return resolved_claims(root, node).get(target_real)


def is_within_claims(root: Path, node: Any, target: str | Path) -> bool:
    """True iff `target` resolves inside the repo and to a file this node claims."""
    return claimed_rel(root, node, target) is not None
