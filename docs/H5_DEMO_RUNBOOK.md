# H5 demo runbook — steer → diff → approve, live

The v4/v5 money shot: a human clicks a unit, steers it in English, Claude Code
edits **through the unit** (confined to its claims), tier0 reruns, the change
surfaces as a **diff-first proposal**, and the human **approves** — all on the
product surface, zero terminal typing after start. This runbook is the exact,
repeatable script; V4.3 is to record it uncut.

The code path is pre-flight-verified end to end (`tests/test_v4_h5_endtoend.py`);
this document is what a human follows on camera.

---

## The unit to steer

**`refundly.gateway`** — `approval.required: true`, `sideEffects: irreversible`
(claims `src/gateway/client.py`). Chosen because the approval gate is the whole
point of H5: an irreversible unit whose edits must be signed.

## Setup (once)

Work on a **scratch copy** so the repo stays clean and the demo is repeatable —
one command builds it (and rebuilds it between takes):

```bash
scripts/demo_reset.sh            # → /tmp/refundly-demo, graph extracted
cd /tmp/refundly-demo
ent serve --operator             # prints the operator start command; opens the Universe (:7373)
```

In a second terminal, in the same directory, start the workload:

```bash
claude               # Claude Code
> operate the map    # triggers the entiendo-operator skill (await_steering loop)
```

## The steps (on camera)

1. **Click `refundly.gateway`** in the Universe. The dossier opens: irreversible,
   `approval required` pill, side-effects irreversible.
2. **Steer.** In the dossier's Steer box, type exactly:

   > `Clamp the refunded amount to the order amount so a refund can never exceed what was paid.`

   Click **Steer**. The dossier flips to *queued — waiting for the operator*.
3. **Claude Code (the operator) picks it up** via `await_steering`, reads the
   unit's scoped context (`get_node_context`: `src/gateway/client.py` + neighbour
   contracts only), and edits **through the unit** — a change confined to
   `execute_refund` in `src/gateway/client.py`, e.g.:

   ```diff
   -def execute_refund(order_id, amount):
   -    return {"order": order_id, "refunded": amount, "irreversible": True}
   +def execute_refund(order_id, amount, order_amount=None):
   +    capped = min(amount, order_amount) if order_amount is not None else amount
   +    return {"order": order_id, "refunded": capped, "irreversible": True}
   ```
4. **The gate holds it back.** Because `approval.required` is set, the operator
   posts the verdict with `proposal=true`: the diff is captured, **the working
   tree reverts to *before*** (nothing is live yet), and the unit's dossier shows
   a **Proposal · awaiting approval** card — the **unified diff + the after-verdict
   together**. On the map, `refundly.gateway` pulses a **gold ring**.

   - **Expected tier0 verdict:** `UNTESTED` — gateway is `external` with no
     `contract.entrypoint` (you never *execute* an irreversible refund in tier0).
     That is correct and expected; H5 is about the approval gate + the diff, not a
     green score. (If you want a GREEN verdict on camera instead, steer
     `refundly.parse_email` — a runnable unit — but it has no approval gate, so
     you lose the proposal step. Gateway is the right choice for H5.)
5. **Review the diff, then click Approve.** The stored `after` is applied to the
   working tree, the proposal clears, the gold ring stops. `src/gateway/client.py`
   now contains the clamped version.
   - (To show the other branch: **Reject** discards the proposal and leaves the
     working tree exactly as it was — nothing ever applied.)

## Expected end state

- `src/gateway/client.py` contains the `order_amount` clamp.
- `entiendo/steering/proposals/` is empty (proposal consumed).
- History carries `proposal: created` then `proposal: approved` events with the
  unit id and proposal id.

## Guardrails you may see live (v6 — expected behaviour, not bugs)

- **Stale-proposal guard:** if anything touches `src/gateway/client.py` while
  the proposal is open, **Approve refuses** with `proposal stale: …` and writes
  nothing. That is the base-hash guard doing its job — reset and re-take.
- **Sandboxed evals:** `ent eval` runs entrypoints in a bounded child process
  (wall-clock timeout + memory limits). A hung unit shows `TIER0_TIMEOUT`
  instead of hanging the session. `--no-sandbox` opts out if ever needed.
- **Claims hook:** in a hooked Claude Code session, an edit outside the steered
  unit's claims is **mechanically denied** (`.claude/hooks/enforce_claims.py`)
  with a message naming the owning unit — the boundary is enforced, not asked.

## Reset (repeat the take)

One command, from the repo root:

```bash
scripts/demo_reset.sh            # rm + re-copy + ent extract
```

If you ran it **in-place** in the repo instead (not recommended), reset with:

```bash
git checkout -- examples/refundly/src/gateway/client.py
rm -rf examples/refundly/entiendo/steering examples/refundly/entiendo/.edit-backups
```

(Both `entiendo/steering/` and `entiendo/.edit-backups/` are gitignored, so a
`git status` after reset is clean.)

## What "done" looks like

One uncut recording: node clicked → steered in English → Claude Code edit
**confined to claims** → tier0 verdict in the Universe → **diff** → **Approve** →
change live. No manual intervention outside the product surface. That recording
is the launch/YC artifact (V4.3), and it is the human's to capture.
