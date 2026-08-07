"""L1/L3 — Composite node versioning. Pin, diff, revert, replay (SPEC.md §5.4).

A node's version is a *composite* hash over everything that can change its
behaviour, bucketed by dimension:

    code    — claimed source files (.py/.ts/.sql/...)
    prompt  — claimed prompt files (.md/.txt/...)
    config  — claimed config files (.yaml/.json/...)
    model   — model identity from the manifest (a version dimension, §7 gap 15)

    composite = hash(code, prompt, config, model)

Because the version is composite, a single node can be pinned and reverted
without touching anything else, and the `composite` is what the timeline scrubs
through. Hashing is deterministic (sorted inputs, content only) so the same tree
always yields the same version.

Two hashing rules keep the composite honest (v6 5.1–5.3):

  - **Secrets never enter the hash.** Config lines whose key matches the secret
    regex (api_key / secret / token / password / credential) contribute the KEY
    but not the VALUE — a rotated secret is not a behaviour change, and secret
    material must never be folded into an artifact that gets committed.
  - **Line endings are normalised** (CRLF → LF) for prompt and config buckets,
    so a checkout on Windows doesn't mint a phantom new version. Nodes whose
    files carried CRLF will recompute once — the timeline shows that as one
    ordinary version event, which is the honest record of the rule change.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .manifest import Node

# The dimensions that compose a node version (order is stable for hashing).
VERSION_DIMENSIONS = ("code", "prompt", "config", "model")

_CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".sql"}
_PROMPT_EXT = {".md", ".txt", ".prompt", ".jinja", ".j2"}
_CONFIG_EXT = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env"}

_SHORT = 12

# v6 5.1 — config keys whose VALUES are secrets: the key still contributes to
# the hash (renaming it is a change) but the value is replaced with a marker.
_SECRET_KEY = re.compile(
    r"^(\s*[\"']?[A-Za-z0-9_.-]*(?:api[-_]?key|secret|token|password|passwd|credential)"
    r"[A-Za-z0-9_.-]*[\"']?\s*[:=])(.*)$", re.IGNORECASE)


def _strip_secrets(text: str) -> str:
    return "\n".join(
        m.group(1) + " <secret>" if (m := _SECRET_KEY.match(line)) else line
        for line in text.split("\n"))


def _normalise(data: bytes, *, secrets: bool) -> bytes:
    """CRLF→LF (5.2/5.3), and secret-value exclusion for config (5.1).

    Binary-ish content that doesn't decode is hashed as-is.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    text = text.replace("\r\n", "\n")
    if secrets:
        text = _strip_secrets(text)
    return text.encode("utf-8")


def _bucket(suffix: str) -> str | None:
    s = suffix.lower()
    if s in _CODE_EXT:
        return "code"
    if s in _PROMPT_EXT:
        return "prompt"
    if s in _CONFIG_EXT:
        return "config"
    return None


def _hash_bytes(chunks: list[bytes]) -> str | None:
    if not chunks:
        return None
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
        h.update(b"\x00")  # length delimiter, so concatenation is unambiguous
    return h.hexdigest()[:_SHORT]


def compute_version(node: Node, root: Path) -> dict[str, Any]:
    """Compute the composite version for a node from its claimed files + model."""
    root = Path(root)
    buckets: dict[str, list[bytes]] = {"code": [], "prompt": [], "config": []}

    from .claims import expand_claims
    for claim in sorted(expand_claims(root, node.claims)):
        path = root / claim
        if not path.exists() or not path.is_file():
            continue
        bucket = _bucket(path.suffix)
        if bucket is None:
            # Uncategorised claimed files still affect behaviour — fold into code.
            bucket = "code"
        data = path.read_bytes()
        if bucket in ("prompt", "config"):
            data = _normalise(data, secrets=(bucket == "config"))
        buckets[bucket].append(data)

    version: dict[str, Any] = {
        "code": _hash_bytes(buckets["code"]),
        "prompt": _hash_bytes(buckets["prompt"]),
        "config": _hash_bytes(buckets["config"]),
        "model": node.raw.get("version", {}).get("model"),
    }
    version["composite"] = composite(version)
    return version


def composite(version: dict[str, Any]) -> str:
    """The hash you pin, diff, revert, and scrub through on the timeline."""
    material = {k: version.get(k) for k in VERSION_DIMENSIONS}
    blob = json.dumps(material, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:_SHORT]


def pin_model(manifest_path: Path, model_id: str) -> str | None:
    """Pin the `model` dimension in a manifest, preserving comments (SPEC §5.4).

    Sets `version.model: <model_id>` with a line-level edit (so hand-authored
    comments survive), creating the `version:` block or the `model:` line if
    absent. Returns the previous model value (None if it wasn't set). The
    fingerprint moves as a result — record it with `ent snapshot`.
    """
    path = Path(manifest_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    def top_level(line: str) -> bool:
        return bool(line) and not line[0].isspace() and line.lstrip().startswith(tuple("abcdefghijklmnopqrstuvwxyz"))

    # locate the top-level `version:` block
    v_idx = next((i for i, ln in enumerate(lines) if ln.rstrip() == "version:" or ln.startswith("version:")), None)
    prev: str | None = None

    if v_idx is not None:
        # scan the block for a `model:` line
        j = v_idx + 1
        model_idx = None
        while j < len(lines) and (not lines[j].strip() or lines[j][0].isspace()):
            if lines[j].lstrip().startswith("model:"):
                model_idx = j
                break
            j += 1
        if model_idx is not None:
            indent = lines[model_idx][: len(lines[model_idx]) - len(lines[model_idx].lstrip())]
            prev = lines[model_idx].split("model:", 1)[1].split("#", 1)[0].strip() or None
            lines[model_idx] = f"{indent}model: {model_id}"
        else:
            lines.insert(v_idx + 1, f"  model: {model_id}")
    else:
        lines.append("version:")
        lines.append(f"  model: {model_id}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prev
