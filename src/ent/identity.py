"""Blesser identity resolution (V3). "AI drafts, human blesses" needs a *who*.

A blessing that records `blessedBy: "unknown"` is not accountability. Identity
resolves from, in order:

  1. an explicit `--as <identity>` (interactive only),
  2. the configured `ent` user — `[user] email|name` in `entiendo/config.toml`,
  3. `git config user.email`.

If none resolve, blessing FAILS — `"unknown"` is no longer a writable value.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Values that are not a real blesser and must never be written.
INVALID_BLESSERS = frozenset({"", "unknown", "none", "null"})


class IdentityError(Exception):
    """No blesser identity could be resolved — blessing must fail."""


def is_valid_blesser(name: str | None) -> bool:
    return bool(name) and name.strip().lower() not in INVALID_BLESSERS


def resolve_identity(root: Path, explicit: str | None = None) -> str:
    """Resolve the blesser, or raise IdentityError. Never returns 'unknown'."""
    for candidate in (explicit, _config_identity(root), _git_email(root)):
        if is_valid_blesser(candidate):
            return candidate.strip()
    raise IdentityError(
        "cannot resolve who is blessing — pass `--as you@example.com`, set "
        "[user] email in entiendo/config.toml, or run `git config user.email <you>`. "
        "Baselines carry a real identity; 'unknown' is not allowed.")


def _config_identity(root: Path) -> str | None:
    path = Path(root) / "entiendo" / "config.toml"
    if not path.exists():
        return None
    try:
        import tomllib  # py3.11+; on 3.10 this source is simply skipped
    except ModuleNotFoundError:
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    user = data.get("user", {}) or {}
    return user.get("email") or user.get("name")


def _git_email(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    value = out.stdout.strip()
    return value or None
