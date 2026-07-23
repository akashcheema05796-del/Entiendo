"""LLM Gateway adapter — claimed by node `llm.gateway`.

The `external` node claims the local adapter you own, never the remote API.
Illustrative only.
"""

from __future__ import annotations

import ent


@ent.node("llm.gateway")
def complete(prompt: str, model: str = "claude-sonnet-4-6") -> dict:
    """Call the model provider. Side effect: external, non-deterministic."""
    # Illustrative only — no real network call.
    return {"text": "", "model": model}
