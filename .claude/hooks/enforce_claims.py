#!/usr/bin/env python3
"""PreToolUse hook — deterministic enforcement of Invariant 8 (PLAN_v6 2.1).

"Edit through the unit" was a convention the agent was asked to follow; this
makes it mechanical. On every Edit/Write/MultiEdit, the hook resolves the target
file against the managed repo's `entiendo/graph.json` claims (via the single
claims authority, `ent.claims` — not a reimplementation) and DENIES:

  - a file no unit claims (unclaimed — the map doesn't know it), and
  - while a steer is active, a file owned by a unit other than the steered one.

EXPLICITLY-unclaimed files are allowed: Invariant 4 has two legitimate states
(claimed, or acknowledged in `entiendo/unclaimed.txt`), and acknowledged glue —
a repo's own tests, docs, scripts — must stay editable. Pattern-matching the
listing (same fnmatch semantics as the extractor) rather than coverage.json's
expansion means a NEW file matching an acknowledged glob is editable too.

With no active steer, claimed files are allowed (any unit) and only unclaimed
files are denied. The steered unit is the Bridge queue's active item:
claimed-but-unresolved first, else the oldest pending request.

Fail-open by design outside managed repos: no `entiendo/graph.json` above the
target → allow (this hook governs operator sessions inside managed trees; it
must never brick an ordinary repo). Plane-owned paths are always allowed:
manifests (`entiendo.node.yaml`), the `entiendo/` artifact tree, and `evals/`
fixtures — those are the control plane's files, not unit interiors, and their
changes are reviewed by humans in PRs. `ENT_HOOK_DISABLE=1` bypasses entirely.

Speaks three editors. Claude Code, Cursor and Antigravity all support blocking
a write before it happens; they disagree only about the JSON. `--format claude`
(default) / `cursor` / `antigravity`, or `ENT_HOOK_FORMAT`. See
docs/builders.md.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


# Which editor is asking. Every one of them can hard-block a write before it
# happens; they just disagree about the JSON. The DECISION is identical — this
# only shapes the answer.
#   claude      Claude Code   PreToolUse  → hookSpecificOutput.permissionDecision
#   cursor      Cursor        preToolUse  → permission
#   antigravity Antigravity   PreToolUse  → decision
FORMATS = ("claude", "cursor", "antigravity")


def _fmt() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == "--format" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith("--format="):
            return arg.split("=", 1)[1]
    return os.environ.get("ENT_HOOK_FORMAT", "claude")


def allow_payload(fmt: str) -> dict:
    if fmt == "cursor":
        return {"permission": "allow"}
    if fmt == "antigravity":
        return {"decision": "allow"}
    return {}


def deny_payload(fmt: str, reason: str) -> dict:
    if fmt == "cursor":
        return {"permission": "deny", "userMessage": reason, "agentMessage": reason}
    if fmt == "antigravity":
        return {"decision": "deny", "reason": reason}
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def target_of(payload: dict) -> str:
    """The file the tool is about to write.

    Defensive on purpose: Claude Code documents `tool_input.file_path`, and the
    other two publish their hook *output* contracts more precisely than their
    input payloads. Accept the plausible spellings, and return '' when none
    match — an unrecognised payload must fail OPEN, never block a session.
    """
    for container in (payload.get("tool_input"), payload.get("toolInput"),
                      payload.get("input"), payload):
        if not isinstance(container, dict):
            continue
        for key in ("file_path", "filePath", "path", "target_file", "targetFile",
                    "absolute_path", "AbsolutePath"):
            value = container.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _allow() -> None:
    print(json.dumps(allow_payload(_fmt())))
    sys.exit(0)


def _deny(reason: str) -> None:
    print(json.dumps(deny_payload(_fmt(), reason)))
    sys.exit(0)


def _managed_root(start: Path) -> Path | None:
    """Nearest ancestor holding entiendo/graph.json — the managed repo root."""
    cur = start if start.is_dir() else start.parent
    for candidate in [cur, *cur.parents]:
        if (candidate / "entiendo" / "graph.json").exists():
            return candidate
    return None


def _steered_unit(root: Path) -> str | None:
    """The Bridge's active steer: claimed-but-unresolved first, else oldest pending."""
    queue = root / "entiendo" / "steering" / "queue.jsonl"
    if not queue.exists():
        return None
    claimed_dir = root / "entiendo" / "steering" / "claimed"
    results_dir = root / "entiendo" / "steering" / "results"
    pending: list[dict] = []
    for line in queue.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        rid = req.get("id", "")
        resolved = (results_dir / f"{rid}.json").exists()
        if resolved:
            continue
        if (claimed_dir / rid).exists():
            return req.get("unit")            # actively being worked — wins
        pending.append(req)
    return pending[0].get("unit") if pending else None


def main() -> None:
    if os.environ.get("ENT_HOOK_DISABLE") == "1":
        _allow()

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        _allow()                              # malformed input — never brick the session

    file_path = target_of(payload)
    if not file_path:
        _allow()

    target = Path(file_path)
    if not target.is_absolute():
        root_hint = (payload.get("cwd") or payload.get("workspaceRoot")
                     or payload.get("workspace_root") or os.getcwd())
        target = Path(root_hint) / target

    root = _managed_root(target)
    if root is None:
        _allow()                              # not a managed repo — fail open

    # plane-owned paths: manifests, the entiendo/ tree, eval fixtures
    try:
        rel = Path(os.path.realpath(target)).relative_to(Path(os.path.realpath(root)))
    except ValueError:
        _allow()
    rel_posix = rel.as_posix()
    if target.name == "entiendo.node.yaml" or rel_posix.startswith(("entiendo/", "evals/")):
        _allow()

    # explicitly-unclaimed (Invariant 4): acknowledged glue stays editable.
    # fnmatch over the listing itself (extractor semantics), so NEW files
    # matching an acknowledged glob are editable too.
    try:
        import fnmatch
        listing = root / "entiendo" / "unclaimed.txt"
        if listing.exists():
            patterns = [line.strip() for line in listing.read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.strip().startswith("#")]
            if any(fnmatch.fnmatch(rel_posix, p) for p in patterns):
                _allow()
    except Exception:
        pass                                  # unreadable listing — fall through to claims

    try:
        from ent import claims as claims_mod   # the single authority (v6 1.4)
        graph = json.loads((root / "entiendo" / "graph.json").read_text(encoding="utf-8"))
    except Exception:
        _allow()                              # no ent install / unreadable graph — fail open

    nodes = [SimpleNamespace(id=n.get("id", "?"), claims=n.get("claims", []) or [])
             for n in graph.get("nodes", [])]
    owner = None
    for node in nodes:
        if claims_mod.is_within_claims(root, node, target):
            owner = node.id
            break

    steered = _steered_unit(root)

    if owner is None:
        _deny(f"{rel_posix} is UNCLAIMED — no unit owns it, so the map cannot "
              "account for this edit. Fix: add it to a unit's `claims` in that "
              "unit's entiendo.node.yaml and re-run `ent extract` (a boundary "
              "change needing human sign-off), or edit through an owning unit.")
    if steered is not None and owner != steered:
        _deny(f"{rel_posix} belongs to unit '{owner}', but the active steer is "
              f"for '{steered}'. Edit through the steered unit only — finish or "
              f"post_verdict the current steer, or steer '{owner}' first.")
    _allow()


if __name__ == "__main__":
    main()
