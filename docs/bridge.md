# The Bridge — steering the Universe into Claude Code (v3 Phase C)

The thesis made real: clicking **Steer** on a unit in the `ent serve` Universe
drives a live Claude Code session — the operator never types in a terminal after
session start. Human = operator, Claude Code = workload, Entiendo = the control
plane between them.

## Transport: plain files, no broker

Deliberately boring and inspectable — everything under `entiendo/steering/`:

```
entiendo/steering/
  queue.jsonl          # append-only log of steering requests (one JSON per line)
  claimed/<id>         # marker: a workload has taken this request
  results/<id>.json    # the verdict the workload posted back
```

A request is **pending** if it is in the queue, not claimed, and not resulted.
`ent serve` streams `pending` + `results` to the browser (poll), so the dossier
flips `queued → verdict` on its own. No websockets to Claude Code (an SSE upgrade
is noted in the plan, not built).

## The loop

```
  Universe (browser)              ent serve                 Claude Code (workload)
  ────────────────────            ─────────                 ──────────────────────
  click unit, type intent  ─POST /api/steer→  enqueue()
        "queued"           ←──────────────    queue.jsonl
                                                  ▲   │
                              GET /api/steering   │   │  await_steering()  ◄── MCP
        poll for result   ──────────────────►     │   └─► {id, unit, instruction}
                                                  │        get_node_context(unit)
                                                  │        apply_edit(unit, files)   (within claims,
                                                  │        reflex reruns → verdict)
        dossier: GREEN,    ←──────────────    results/<id>.json  ◄─ post_verdict(id, outcome)
        bubble flashes
```

- **`POST /api/steer {unit, instruction}`** → `steering.enqueue`; the UI shows *queued*.
- **`GET /api/steering`** → `{pending, results}`; the UI polls it (~1.5 s) and, when
  a result for its request id appears, updates the verdict and flashes the unit.
- **MCP `await_steering(timeout_s)`** → the next pending request (bounded, so the
  call returns; the workload just loops).
- **MCP `post_verdict(request_id, outcome)`** → writes `results/<id>.json`. The
  outcome now carries a **real diff** (per-file unified diff), the **before/after
  verdict**, and — when golden fixtures exist — the **behaviour delta** (spec §6).

## Approval, for real (H0.3)

An edit to a unit whose `approval.required` is set is not applied live. The
operator calls `post_verdict(request_id, outcome, proposal=true)`; the diff is
captured, the working tree reverts to *before*, and the change waits under
`entiendo/steering/proposals/<id>.json`:

- **`GET /api/proposals`** → the open proposals (diff + behaviour delta + verdict).
- **`POST /api/proposals/<id>/approve`** → applies the stored `after` to the tree.
- **`POST /api/proposals/<id>/reject`** → discards it (the tree is already at *before*).

Both approve and reject write a history event. It is a boring stored-diff apply —
no live-tree magic, no git stash.

## Diff-first approval on the canvas (H5)

The gate is signed from the Universe, not a summary. A unit with a proposal
waiting draws a **pulsing gold ring** on the map (`pendingApproval`); every other
gated unit shows a small static gate arc. Opening it loads the proposal into the
dossier — the **unified diff, the behaviour delta, and the after-verdict
together** — so the human approves the change they can *see*, then **Approve**
(`POST /api/proposals/<id>/approve`) or **Reject** (`POST …/reject`). A static
`ent render` has no server to act against, so those actions are inert there.

All are pure functions over `root` (`src/ent/steering.py`), unit-tested without a
transport (`tests/test_steering.py`), including a scripted-agent dry-run of the
whole loop ending in a GREEN verdict.

## Running it

```bash
ent serve --operator          # serves the Universe + prints the start command
# then, in the same repo:
claude                        # start Claude Code
> operate the map             # triggers the entiendo-operator skill
```

The `entiendo-operator` skill (`.claude/skills/entiendo-operator/`) runs the
workload loop: `await_steering → get_node_context → apply_edit → post_verdict`.
It edits **through the unit** — if an instruction needs a file outside the unit's
`claims`, it proposes a boundary change (and posts that as the verdict) rather
than writing around the boundary. A RED verdict is reported, never hidden; the
approval gate stays the operator's to sign.
