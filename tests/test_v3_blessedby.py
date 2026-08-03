"""V3 — accountability: blessedBy + kill the CI bless bypass (PLAN_v5).

"AI drafts, human blesses" is enforced, not aspirational: blessing needs an
interactive TTY (even with --yes, no env-var bypass), records a real identity
(--as → entiendo/config.toml → git user.email), and "unknown" is never writable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import baselines, identity  # noqa: E402
from ent.identity import IdentityError, is_valid_blesser, resolve_identity  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


# --------------------------------------------------------------------------- #
# identity resolution chain
# --------------------------------------------------------------------------- #

def test_explicit_identity_wins(tmp_path: Path) -> None:
    assert resolve_identity(tmp_path, explicit="mehar@entiendo.dev") == "mehar@entiendo.dev"


def test_config_identity_used_when_no_explicit(tmp_path: Path) -> None:
    (tmp_path / "entiendo").mkdir()
    (tmp_path / "entiendo" / "config.toml").write_text('[user]\nemail = "cfg@entiendo.dev"\n')
    if sys.version_info < (3, 11):
        pytest.skip("tomllib requires 3.11; config source is skipped on 3.10")
    assert resolve_identity(tmp_path, explicit=None) == "cfg@entiendo.dev"


def test_git_email_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(identity, "_config_identity", lambda root: None)
    monkeypatch.setattr(identity, "_git_email", lambda root: "git@entiendo.dev")
    assert resolve_identity(tmp_path) == "git@entiendo.dev"


def test_no_identity_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(identity, "_config_identity", lambda root: None)
    monkeypatch.setattr(identity, "_git_email", lambda root: None)
    with pytest.raises(IdentityError):
        resolve_identity(tmp_path)


def test_unknown_is_never_valid() -> None:
    for bad in ("", "unknown", "UNKNOWN", "none", None):
        assert not is_valid_blesser(bad)
    assert is_valid_blesser("mehar@entiendo.dev")


# --------------------------------------------------------------------------- #
# write guard: "unknown" is not writable
# --------------------------------------------------------------------------- #

def test_write_bless_rejects_unknown(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        baselines.write_bless(tmp_path, "demo.node", dataset_rel="g.jsonl", sha="abc",
                              rows=1, blessed_by="unknown", blessed_at="t0")
    with pytest.raises(ValueError):
        baselines.write_bless(tmp_path, "demo.node", dataset_rel="g.jsonl", sha="abc",
                              rows=1, blessed_by="", blessed_at="t0")


def test_write_bless_accepts_real_identity(tmp_path: Path) -> None:
    path = baselines.write_bless(tmp_path, "demo.node", dataset_rel="g.jsonl", sha="abc",
                                 rows=1, blessed_by="mehar@entiendo.dev", blessed_at="t0")
    assert path.exists()
    assert baselines.read_bless(tmp_path, "demo.node")["blessedBy"] == "mehar@entiendo.dev"


# --------------------------------------------------------------------------- #
# the CI bypass is closed: bless from a non-TTY fails
# --------------------------------------------------------------------------- #

def test_bless_from_non_tty_fails() -> None:
    # stdin is not a tty (DEVNULL) — the CI case. Even --yes must be refused.
    proc = subprocess.run(
        ["ent", "bless", "refundly.parse_email", "--yes", "--root", str(REFUNDLY)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0
    assert "interactive session" in (proc.stdout + proc.stderr).lower()


def test_no_env_var_bypass_exists() -> None:
    """Behavioural (v6 5.5): even with every plausible escape-hatch env var set,
    a non-TTY bless is still refused. A source-string grep only proved the
    absence of a spelling; this proves the absence of the behaviour."""
    import os
    env = {**os.environ,
           "ENT_ALLOW_NONINTERACTIVE": "1", "ENT_BLESS_OK": "1",
           "ENT_NONINTERACTIVE": "1", "ALLOW_NONINTERACTIVE": "1",
           "CI": "true", "FORCE": "1", "YES": "1"}
    proc = subprocess.run(
        ["ent", "bless", "refundly.parse_email", "--yes", "--root", str(REFUNDLY)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, env=env)
    assert proc.returncode == 3
    assert "interactive session" in (proc.stdout + proc.stderr).lower()
    # and nothing was written — the tree carries no new bless record
    assert not (REFUNDLY / "entiendo/baselines/refundly.parse_email.bless.json").exists()
