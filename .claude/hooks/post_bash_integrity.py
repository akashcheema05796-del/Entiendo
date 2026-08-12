#!/usr/bin/env python3
"""PostToolUse hook on Bash — detect-and-revert golden tampering (Phase 2).

Predict-and-block on shell strings is unwinnable (`python -c`, `sed -i`,
`tee`, heredocs, `git checkout <sha> --` all rewrite files without an Edit
tool call). So this runs AFTER every Bash call, stdlib-only and with no
package dependency (it must work in a fresh clone before `pip install`):

  1. find every `entiendo/goldens.lock` under the project dir;
  2. for each root, recompute the SHA-256 of every locked file and scan
     `evals/**/golden*` for additions;
  3. on any mismatch: restore tracked files with `git checkout --`, delete
     untracked rogue goldens, and exit 2 so the agent sees exactly what
     happened and why.

`ENTIENDO_BLESS_IN_PROGRESS=1` allows a legitimate human-driven re-bless to
flow through. This hook is the LOCAL feedback loop; the enforcement of
record stays in CI (`integrity.yml` + the committed lock diff).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist"}


def _project_dir() -> Path:
    for var in ("CLAUDE_PROJECT_DIR", "PWD"):
        v = os.environ.get(var)
        if v and Path(v).is_dir():
            return Path(v)
    return Path.cwd()


def _find_locks(base: Path) -> list[Path]:
    locks: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if Path(dirpath).name == "entiendo" and "goldens.lock" in filenames:
            locks.append(Path(dirpath) / "goldens.lock")
    return locks


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_root(lock: Path) -> tuple[list[str], list[str]]:
    """(tampered_rel_paths, rogue_rel_paths) for one project root."""
    root = lock.parent.parent
    try:
        locked: dict[str, str] = json.loads(lock.read_text()).get("files", {})
    except ValueError:
        return (["entiendo/goldens.lock"], [])          # corrupt lock = tampered
    tampered: list[str] = []
    for rel, sha in locked.items():
        f = root / rel
        if not f.exists() or _sha256(f) != sha:
            tampered.append(rel)
    rogue: list[str] = []
    evals_dir = root / "evals"
    if evals_dir.is_dir():
        for p in evals_dir.rglob("golden*"):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and rel not in locked:
                rogue.append(rel)
    return (sorted(tampered), sorted(rogue))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(root),
                          capture_output=True, text=True, timeout=30)


def _revert(root: Path, tampered: list[str], rogue: list[str]) -> list[str]:
    notes: list[str] = []
    if tampered:
        # restore from HEAD, not the index — `git checkout <sha> -- goldens`
        # stages the old content, so an index-based restore would keep it
        done = _git(root, "checkout", "HEAD", "--", *tampered)
        notes.append(f"restored {len(tampered)} file(s) from git"
                     if done.returncode == 0 else
                     f"git restore FAILED ({done.stderr.strip()[:120]}) — restore by hand")
    for rel in rogue:
        try:
            (root / rel).unlink()
            notes.append(f"deleted rogue golden {rel}")
        except OSError as exc:
            notes.append(f"could not delete {rel}: {exc}")
    return notes


def main() -> None:
    if os.environ.get("ENTIENDO_BLESS_IN_PROGRESS") == "1":
        sys.exit(0)                       # a human is legitimately re-pinning
    try:
        json.load(sys.stdin)              # payload unused; tolerate anything
    except Exception:
        pass

    problems: list[str] = []
    for lock in _find_locks(_project_dir()):
        tampered, rogue = _check_root(lock)
        if not tampered and not rogue:
            continue
        root = lock.parent.parent
        notes = _revert(root, tampered, rogue)
        what = ", ".join(tampered + rogue)
        problems.append(f"[{root}] {what} — {'; '.join(notes)}")

    if problems:
        print("Protected golden files were modified by a shell command; "
              "changes reverted. Do not attempt to modify graded answers — "
              "ground truth changes go through `ent goldens bless` in a "
              "reviewed PR.\n" + "\n".join(problems), file=sys.stderr)
        sys.exit(2)                       # surfaced to the agent as feedback
    sys.exit(0)


if __name__ == "__main__":
    main()
