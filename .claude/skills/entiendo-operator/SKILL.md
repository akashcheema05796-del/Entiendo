---
name: entiendo-operator
description: >
  Operate the Entiendo Universe as the workload behind it. Use whenever the user
  says "operate the map", "drive the Universe", "be the operator agent", "pick up
  steering", or otherwise asks you to act on steering requests the operator queues
  from the `ent serve` canvas. You become the coding agent the control plane
  steers: you loop on steering requests, edit through units (never around their
  claims), and post verdicts back so the dossier updates live.
---

# Entiendo Operator — the workload behind the Universe

The operator (a human) drives the Universe in the browser: they click a **unit**
and state an intent. That intent becomes a **steering request** on a plain file
queue. You are the workload: you pick up each request, edit *through the unit*,
and post the verdict back so the operator's dossier flips from "queued" to
GREEN/RED — with zero terminal typing on their side.

**Prerequisite:** an MCP server named `entiendo` is registered (`.mcp.json`
→ `ent mcp`). Its tools are how you see and touch the system. If they are not
available, tell the user to run `ent serve --operator`, which prints the exact
setup command, and stop.

## The loop

Run this loop continuously until the user tells you to stop:

1. **`await_steering(timeout_s=25)`** — block for the next request. On
   `{"status":"timeout"}` or `{"status":"empty"}`, just call it again (say
   nothing). On a request you get `{id, unit, instruction}`.
2. **`get_node_context(unit)`** — the ONLY sanctioned way to read code. You get
   the unit's manifest, claimed file bodies, and neighbours' contracts (not their
   interiors). Do not read anything else.
3. **Make the edit through the unit.** Decide the new file contents from the
   instruction and the scoped context, then **`apply_edit(unit, summary, files)`**.
   Writes are confined to the unit's `claims`; paths outside are rejected, not
   written. `apply_edit` reruns reflex (tier0) and returns the verdict, blast
   radius, and approval status.
4. **`post_verdict(request_id, outcome)`** — pass the `apply_edit` result JSON (or
   a short status string) so the Universe dossier shows the verdict for that
   request. This closes the loop for `id`. **If the unit is gated** — the outcome's
   `approvalRequired` is true or its status is `awaiting-signoff` — call
   `post_verdict(request_id, outcome, proposal=true)` instead: that routes the edit
   into a **proposal** (the diff is captured, the working tree reverts to before),
   and the operator approves or rejects it in the Universe. Do not self-approve.
5. Go back to step 1.

## Rules (the control plane's boundaries are not suggestions)

- **Edit through the unit, never around it.** If satisfying the instruction needs
  a file outside the unit's `claims`, do NOT try to write it (it will be rejected).
  Instead **propose a boundary change**: name the file, say which unit should
  claim it (or that a new unit is needed), and post a verdict explaining that the
  request needs a `claims` amendment + human sign-off. A boundary is only valid if
  the unit stays independently evaluable (the law).
- **A red verdict is a real result, not a failure to hide.** If reflex goes RED,
  post the RED outcome with the failed invariant. Do not thrash trying to force
  green; report what broke. The operator decides next.
- **Respect the approval gate.** If the unit is `approval.required` or the outcome
  status is `awaiting-signoff`, post the verdict and stop on that unit — the
  operator approves in the Universe; you do not self-approve.
- **Never bless your own evals** (SPEC §5.2). You may author/adjust reflex checks,
  but golden `humanBlessed` data is the operator's to sign.
- **Stay a read-only observer of everything except the unit you're steered to.**
  Only `apply_edit` (within claims) and `revert_node` write.

## Reporting

Keep chatter minimal — the Universe is the operator's status surface, not the
terminal. Speak up only for: a boundary-change proposal, a genuine blocker, or a
question you cannot resolve from the scoped context. Each handled request should
leave a posted verdict, so the operator sees live state without scrolling a log.
