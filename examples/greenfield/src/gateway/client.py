"""LLM Gateway adapter — claimed by node `llm.gateway`.

The `external` node claims the local adapter you own, never the remote API.
Illustrative only.
"""

from __future__ import annotations

import ent


@ent.node("llm.gateway")
def complete(request: dict) -> dict:
    """Call the model provider. Side effect: external, non-deterministic.

    One dict in, one dict out (Phase 7 §1.1): {prompt, model?} -> {text, model}.
    """
    prompt = request.get("prompt", "")
    model = request.get("model", "claude-sonnet-4-6")
    # Illustrative only — no real network call.
    result = {"text": "", "model": model}
    # Meter spend onto this node's span (the cost meter). A no-op if the caller
    # isn't inside a capture()/OTel context, so it never affects the request path.
    ent.record(cost_usd=0.01, tokens=len(prompt.split()))
    return result
