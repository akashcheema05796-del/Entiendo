"""Tiny helpers for stamping history events with a commit + timestamp.

Both degrade gracefully: outside a git repo, `short_commit` returns None; the
timestamp is always available. Kept isolated so the rest of the code stays pure
and testable (callers can inject values instead).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


def short_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
