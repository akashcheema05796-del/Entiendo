"""The boundary hook speaks every builder that can block a write.

Claude Code, Cursor and Antigravity all support a pre-write hook that can hard-
block; they disagree only about the JSON. The DECISION is one implementation —
these guard the three answer shapes and the defensive input parsing.

Output contracts, from each vendor's docs (fetched 2026-08-08):
  Claude Code  hookSpecificOutput.permissionDecision = "deny"
  Cursor       permission = "deny"          (.cursor/hooks.json, preToolUse)
  Antigravity  decision   = "deny"          (.agents/hooks.json, PreToolUse)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.extractor import extract, write_artifacts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".claude" / "hooks" / "enforce_claims.py"
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def managed(tmp_path: Path) -> Path:
    root = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, root)
    write_artifacts(extract(root), root)
    return root


def _run(payload: dict, fmt: str | None = None) -> dict:
    cmd = [sys.executable, str(HOOK)]
    if fmt:
        cmd += ["--format", fmt]
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True,
                          text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _denied(out: dict, fmt: str) -> bool:
    if fmt == "cursor":
        return out.get("permission") == "deny"
    if fmt == "antigravity":
        return out.get("decision") == "deny"
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


@pytest.mark.parametrize("fmt", ["claude", "cursor", "antigravity"])
def test_unclaimed_file_is_denied_in_every_builder(managed: Path, fmt: str) -> None:
    (managed / "rogue.py").write_text("x = 1\n")
    out = _run({"tool_name": "Write", "cwd": str(managed),
                "tool_input": {"file_path": str(managed / "rogue.py")}}, fmt)
    assert _denied(out, fmt), out
    blob = json.dumps(out)
    assert "UNCLAIMED" in blob and "claims" in blob      # the reason travels


@pytest.mark.parametrize("fmt", ["claude", "cursor", "antigravity"])
def test_claimed_file_is_allowed_in_every_builder(managed: Path, fmt: str) -> None:
    out = _run({"tool_name": "Write", "cwd": str(managed),
                "tool_input": {"file_path": str(managed / "src/gateway/client.py")}}, fmt)
    assert not _denied(out, fmt), out


@pytest.mark.parametrize("key", ["file_path", "filePath", "path", "absolute_path"])
def test_input_parsing_tolerates_field_spellings(managed: Path, key: str) -> None:
    """Vendors document their hook OUTPUT precisely and their input payloads
    loosely, so the parse accepts the plausible spellings."""
    (managed / "rogue.py").write_text("x = 1\n")
    out = _run({"tool_name": "Write", "cwd": str(managed),
                "toolInput": {key: str(managed / "rogue.py")}}, "cursor")
    assert out.get("permission") == "deny", out


def test_unrecognised_payload_fails_open(managed: Path) -> None:
    """An input shape we cannot read must never block a session."""
    for fmt in ("claude", "cursor", "antigravity"):
        out = _run({"tool_name": "Write", "cwd": str(managed),
                    "somethingElse": {"mystery": "value"}}, fmt)
        assert not _denied(out, fmt), (fmt, out)


def test_default_format_is_claude_code(managed: Path) -> None:
    (managed / "rogue.py").write_text("x = 1\n")
    out = _run({"tool_name": "Write", "cwd": str(managed),
                "tool_input": {"file_path": str(managed / "rogue.py")}})
    assert (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"
