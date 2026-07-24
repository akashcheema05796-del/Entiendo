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
    result = {"text": "", "model": model}
    # Meter spend onto this node's span (the cost meter). A no-op if the caller
    # isn't inside a capture()/OTel context, so it never affects the request path.
    ent.record(cost_usd=0.01, tokens=len(prompt.split()))
    return result
