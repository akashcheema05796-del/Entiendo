"""Repo-wide golden integrity: the hash manifest (hardening plan, Phase 1).

Two layers protect ground truth, deliberately distinct:

- **Blessing** (`ent bless`, baselines.py) — a human signs ONE dataset's
  content as expected behaviour. Signature void on change; gating requires it.
- **The manifest** (this module, `entiendo/goldens.lock`) — a repo-wide net
  over EVERY golden file, blessed or not: SHA-256 per file, sorted paths.
  Grading refuses to run when reality disagrees with the lock, and because
  the lock is committed, any legitimate change to ground truth shows up as a
  reviewable diff in the PR. The trust root is git history + branch
  protection + CI — not a key an agent could read.

Discovery is two-source, so nothing slips between:
  1. every `evals.tier1[].dataset` declared by a manifest (the graded set),
  2. every file matching `evals/**/golden*` on disk (so a ROGUE golden —
     planted but not yet declared — is still caught as an addition).

No lock + goldens present = "unprotected", which is a visible state, not an
error — partial adoption stays possible; `ent goldens verify --require-lock`
turns it into a failure for repos (like this one) that have opted in.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .manifest import discover, load

SCHEMA_VERSION = 1
LOCK_REL = "entiendo/goldens.lock"

# roots verified once per process (the check guards every graded row — it
# must not cost a rehash per row)
_VERIFIED: set[str] = set()


class GoldenTamperError(RuntimeError):
    """The golden files on disk disagree with entiendo/goldens.lock."""


def lock_path(root: Path) -> Path:
    return Path(root) / LOCK_REL


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def golden_files(root: Path) -> list[str]:
    """Sorted repo-relative paths of every golden file, from both sources."""
    root = Path(root)
    found: set[str] = set()
    for mpath in discover(root):
        try:
            raw = load(mpath)
        except Exception:
            continue                        # invalid manifest → validate's problem
        for entry in ((raw or {}).get("evals", {}) or {}).get("tier1", []) or []:
            ds = entry.get("dataset") if isinstance(entry, dict) else None
            if ds and (root / ds).exists():
                found.add(Path(ds).as_posix())
    evals_dir = root / "evals"
    if evals_dir.is_dir():
        for p in evals_dir.rglob("golden*"):
            if p.is_file():
                found.add(p.relative_to(root).as_posix())
    return sorted(found)


def compute_manifest(root: Path) -> dict[str, Any]:
    root = Path(root)
    from . import __version__
    from .gitinfo import now_iso
    return {
        "schemaVersion": SCHEMA_VERSION,
        "createdAt": now_iso(),
        "toolVersion": __version__,
        "files": {rel: _sha256(root / rel) for rel in golden_files(root)},
    }


def write_lock(root: Path) -> Path:
    p = lock_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest = compute_manifest(root)
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _VERIFIED.discard(str(Path(root).resolve()))     # re-verify against the new lock
    return p


def diff_against_lock(root: Path) -> dict[str, list[str]] | None:
    """None if no lock; else {'changed': [...], 'added': [...], 'missing': [...]}."""
    root = Path(root)
    p = lock_path(root)
    if not p.exists():
        return None
    try:
        locked: dict[str, str] = json.loads(p.read_text()).get("files", {})
    except ValueError as exc:
        raise GoldenTamperError(f"{LOCK_REL} is unreadable ({exc}) — regenerate "
                                "with `ent goldens bless` via PR review") from exc
    actual = {rel: _sha256(root / rel) for rel in golden_files(root)}
    return {
        "changed": sorted(r for r in locked.keys() & actual.keys()
                          if locked[r] != actual[r]),
        "added": sorted(actual.keys() - locked.keys()),
        "missing": sorted(locked.keys() - actual.keys()),
    }


def verify_manifest(root: Path, *, require_lock: bool = False) -> str:
    """Verify disk against the lock. Returns a status line; raises
    GoldenTamperError on any mismatch (fatal by design, never a warning)."""
    diff = diff_against_lock(root)
    if diff is None:
        if require_lock and golden_files(root):
            raise GoldenTamperError(
                f"no {LOCK_REL} but golden files exist — ground truth is "
                "unpinned. Run `ent goldens bless` (through PR review).")
        return "no goldens.lock — nothing pinned"
    problems = {k: v for k, v in diff.items() if v}
    if problems:
        detail = "; ".join(f"{kind}: {', '.join(paths)}"
                           for kind, paths in problems.items())
        raise GoldenTamperError(
            f"golden files disagree with {LOCK_REL} — {detail}. If this "
            "change is legitimate, run `ent goldens bless` and let the lock "
            "diff be reviewed in the PR; otherwise restore the files "
            f"(`git checkout -- evals {LOCK_REL}`)")
    n = len(json.loads(lock_path(root).read_text()).get("files", {}))
    return f"{n} golden file(s) match {LOCK_REL}"


def ensure_verified(root: Path) -> None:
    """The per-process cached check every golden READ path calls. A repo
    without a lock passes (unprotected is visible, not fatal); a repo whose
    goldens disagree with its lock cannot be graded."""
    key = str(Path(root).resolve())
    if key in _VERIFIED:
        return
    verify_manifest(root)                    # raises on tamper
    _VERIFIED.add(key)
