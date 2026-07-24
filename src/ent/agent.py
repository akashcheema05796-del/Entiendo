"""L5 — the model that edits through the node (the AI-assisted edit loop).

Given a node's scoped context (its manifest, claimed file bodies, neighbour
contracts, recent evals) and a natural-language instruction, propose edits — and
only to files the node `claims`. The model never sees the rest of the repo; the
manifest is the retrieval index (SPEC.md §6).

Uses the official Anthropic SDK (`anthropic`) on Claude Opus 5, with structured
outputs so the response is a validated `{summary, files: [{path, content}]}`
object. Degrades cleanly: with no SDK installed or no credentials configured, it
raises AgentUnavailable and the server surfaces that — the read-only explorer and
manual evals keep working.
"""

from __future__ import annotations

import json
from typing import Any

from .editloop import Context

DEFAULT_MODEL = "claude-opus-5"

_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "files"],
        "properties": {
            "summary": {"type": "string"},
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path", "content"],
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
        },
    },
}


class AgentUnavailable(RuntimeError):
    """The editing model could not be reached (no SDK, no credentials, or API error)."""


def _client(injected: Any | None):
    if injected is not None:
        return injected
    try:
        import anthropic
    except ImportError as exc:
        raise AgentUnavailable(
            "the `anthropic` SDK is not installed — `pip install -e '.[serve]'`"
        ) from exc
    try:
        return anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY or an `ant` profile
    except Exception as exc:  # pragma: no cover - construction rarely fails
        raise AgentUnavailable(f"could not construct the Anthropic client: {exc}") from exc


def _system_prompt(ctx: Context) -> str:
    contract = ctx.manifest.get("contract", {})
    invariants = contract.get("invariants", []) or []
    neighbours = "\n".join(
        f"  - {nid}: {json.dumps(c)}" for nid, c in ctx.neighbour_contracts.items()
    ) or "  (none)"
    inv = "\n".join(f"  - {i}" for i in invariants) or "  (none)"
    return (
        "You edit ONE node of a system, through its contract.\n"
        f"Node: {ctx.node_id}\n"
        "You may ONLY edit files this node claims. Do not touch anything else — a\n"
        "change outside the claims requires a separate boundary-change proposal.\n\n"
        f"Claimed files (the only files you may edit):\n"
        + "\n".join(f"  - {p}" for p in ctx.claimed_files)
        + "\n\nThe node's contract invariants MUST continue to hold:\n" + inv
        + "\n\nImmediate neighbours (contracts only — you cannot change these):\n" + neighbours
        + "\n\nReturn only the files you changed, each with its FULL new content. "
        "Keep the code in the style of the surrounding code. Do not add files."
    )


def _user_prompt(ctx: Context, instruction: str) -> str:
    files = "\n\n".join(
        f"=== {path} ===\n{body}" for path, body in ctx.claimed_files.items()
    )
    return (
        f"Current claimed files:\n\n{files}\n\n"
        f"Recent evals: {json.dumps(ctx.recent_evals[-3:])}\n\n"
        f"Requested change:\n{instruction}"
    )


def _text_of(response: Any) -> str:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    raise AgentUnavailable("model returned no text block")


def propose_edit(
    ctx: Context,
    instruction: str,
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Ask the model for edits to a node's claimed files.

    Returns {summary, files: {path: new_content}, rejected: [paths outside claims]}.
    Paths the model tries to write outside `claims` are rejected, never applied.
    """
    cl = _client(client)
    try:
        response = cl.messages.create(
            model=model,
            max_tokens=16000,
            system=_system_prompt(ctx),
            messages=[{"role": "user", "content": _user_prompt(ctx, instruction)}],
            output_config={"format": _OUTPUT_SCHEMA},
        )
    except AgentUnavailable:
        raise
    except Exception as exc:  # API/auth/network errors
        raise AgentUnavailable(f"model call failed: {exc}") from exc

    data = json.loads(_text_of(response))
    claims = set(ctx.claimed_files)
    files: dict[str, str] = {}
    rejected: list[str] = []
    for entry in data.get("files", []):
        path = entry["path"]
        (files.__setitem__(path, entry["content"]) if path in claims
         else rejected.append(path))
    return {"summary": data.get("summary", ""), "files": files, "rejected": rejected}
