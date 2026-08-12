"""Phase 2 — the PostToolUse detect-and-revert hook, attacked every way.

Predict-and-block on shell strings is unwinnable, so the guarantee under
test is the honest one: after ANY shell command that rewrites a golden —
`python -c`, `sed -i`, `tee`, a heredoc, `git checkout <sha> --` — the hook
restores the files, deletes rogue additions, and exits 2 with the warning
the agent will read. A legitimate re-bless (`ENTIENDO_BLESS_IN_PROGRESS=1`)
flows through untouched.

The hook is stdlib-only and package-independent — these tests run it exactly
as Claude Code would: a subprocess with a JSON payload on stdin.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent import integrity  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
HOOK = REPO_ROOT / ".claude" / "hooks" / "post_bash_integrity.py"
GOLDEN = "evals/refundly.decide/golden_v3.jsonl"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A git repo with pinned goldens — the state a fresh clone is in."""
    root = tmp_path / "proj"
    shutil.copytree(REFUNDLY, root)
    integrity.write_lock(root)
    def git(*a: str) -> None:
        subprocess.run(["git", *a], cwd=str(root), capture_output=True,
                       text=True, timeout=30, check=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "pinned")
    return root


def _hook(root: Path, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    e = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), **(env or {})}
    e.pop("ENTIENDO_BLESS_IN_PROGRESS", None) if env is None else None
    return subprocess.run([sys.executable, str(HOOK)],
                          input=json.dumps({"tool_name": "Bash"}),
                          capture_output=True, text=True, timeout=60, env=e)


def _sh(root: Path, script: str) -> None:
    subprocess.run(["bash", "-c", script], cwd=str(root), capture_output=True,
                   text=True, timeout=30)


def _golden_matches_lock(root: Path) -> bool:
    locked = json.loads((root / "entiendo/goldens.lock").read_text())["files"]
    return integrity._sha256(root / GOLDEN) == locked[GOLDEN]


BYPASSES = {
    "python -c": f"python3 -c \"open('{GOLDEN}','w').write('rigged')\"",
    "sed -i": f"sed -i 's/42/43/' {GOLDEN}",
    "tee": f"echo rigged | tee {GOLDEN} > /dev/null",
    "heredoc": f"cat > {GOLDEN} <<'EOF'\nrigged\nEOF",
    "append": f"echo '{{\"name\": \"smuggled\"}}' >> {GOLDEN}",
}


@pytest.mark.parametrize("name,script", sorted(BYPASSES.items()))
def test_every_shell_bypass_is_reverted(repo: Path, name: str, script: str) -> None:
    _sh(repo, script)
    assert not _golden_matches_lock(repo), f"{name}: the bypass itself failed"
    proc = _hook(repo)
    assert proc.returncode == 2, f"{name}: hook must exit 2"
    assert "reverted" in proc.stderr and "graded answers" in proc.stderr
    assert _golden_matches_lock(repo), f"{name}: golden not restored"


def test_git_checkout_of_an_old_sha_is_reverted(repo: Path) -> None:
    """`git checkout <sha> -- goldens/` pulls historic content into BOTH the
    worktree and the index — the sneakiest editor-free rewrite, because a
    plain index-based restore would keep the tamper. The hook restores from
    HEAD. (A tamper that is already COMMITTED is beyond any local hook — that
    is exactly what the integrity.yml CI check exists for.)"""
    old = repo / GOLDEN
    original = old.read_text()
    old.write_text("historic truth\n")
    _sh(repo, "git add -A && git commit -qm old-truth")
    old.write_text(original)
    _sh(repo, "git add -A && git commit -qm blessed-state")
    _sh(repo, f"git checkout -q HEAD~1 -- {GOLDEN}")   # worktree AND index poisoned
    assert not _golden_matches_lock(repo)
    proc = _hook(repo)
    assert proc.returncode == 2
    assert _golden_matches_lock(repo)


def test_a_rogue_untracked_golden_is_deleted(repo: Path) -> None:
    rogue = repo / "evals" / "refundly.decide" / "golden_planted.jsonl"
    _sh(repo, f"echo '{{}}' > {rogue.relative_to(repo)}")
    proc = _hook(repo)
    assert proc.returncode == 2
    assert "golden_planted.jsonl" in proc.stderr
    assert not rogue.exists()


def test_legitimate_bless_in_progress_is_allowed(repo: Path) -> None:
    (repo / GOLDEN).write_text("being re-blessed by a human\n")
    proc = _hook(repo, env={"ENTIENDO_BLESS_IN_PROGRESS": "1"})
    assert proc.returncode == 0
    assert (repo / GOLDEN).read_text() == "being re-blessed by a human\n"


def test_clean_repo_is_silent(repo: Path) -> None:
    proc = _hook(repo)
    assert proc.returncode == 0 and not proc.stderr.strip()


def test_fresh_clone_is_protected_with_zero_setup() -> None:
    """The whole config rides in the committed repo: settings.json wires both
    hooks and carries permissions.deny for the golden paths — nothing to run
    before protection holds."""
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    deny = settings["permissions"]["deny"]
    assert "Edit(**/evals/**/golden*)" in deny
    assert "Write(**/entiendo/goldens.lock)" in deny
    post = settings["hooks"]["PostToolUse"]
    assert any(h["matcher"] == "Bash" and
               "post_bash_integrity" in h["hooks"][0]["command"] for h in post)
    pre = settings["hooks"]["PreToolUse"]
    assert any("enforce_claims" in h["hooks"][0]["command"] for h in pre)
