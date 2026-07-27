# Entiendo v4 — Implementation Plan
## "The Universe becomes real"

**What v4 is:** v3 shipped the control plane's *truth* (manifests, reconciler,
evals, fingerprints, steering). v4 makes that truth **visible, legible, and
steerable by anyone** — and closes the backend gaps the audit found between
what the spec promises and what the code delivers.

**The audit findings this plan answers (July 27 review):**

| # | Finding | Layer |
|---|---|---|
| 1 | `interior:` (process, tools, maxSteps) never reaches `build_view()` — agentic units render as opaque orbs | backend + frontend |
| 2 | Budgets/cost never leave the manifest; no cost overlay despite spec calling cost "first-class on the health lens" | backend + frontend |
| 3 | Trace data records latency + cost per hop, but the Trace lens shows only a count in the legend — no playback | frontend |
| 4 | Timeline lens is a ◷ badge + six hash rows — no scrubbing | frontend |
| 5 | Steer results carry a verdict but **no diff** — you cannot see what the agent changed (spec §6 promised before/after) | backend + frontend |
| 6 | Approve button is fake — prints a sentence, no API behind it | backend + frontend |
| 7 | Dossier is engineer-only: ids, hashes, invariant code; no plain-language reading of a unit | backend (task field) + frontend |
| 8 | Canvas: no zoom/pan, no touch, no search, no keyboard access, groups expand but never re-collapse, no URL state | frontend |
| 9 | Visual identity is the generic dark-dashboard default; nothing earns "mission control" | frontend |
| 10 | `examples/refundly` is 3 units, not the planned 6-stage pipeline — approval gate + irreversible side-effects never exercised | reference data |

**Ordering principle (unchanged from v3): moat before demo.**
Backend truth first (H0), reference data second (H1), then the surface (H2–H5).
Building the new UI against an incomplete view model just moves the lie.

---

## Phase H0 — View-model completeness + the missing APIs (1–2 days) **[prerequisite]**

Everything the UI will show must exist in `build_view()` first.

### H0.1 View model
- `build_view()` node views gain:
  - `interior`: `{process, tools: [{name, crosses}], maxSteps}` (verbatim from manifest; absent for non-agentic units)
  - `budgets`: `{p95LatencyMs, costPerCallUsd, tokensPerCall}` + **measured** values derived from trace hops (avg/p95 latency, avg cost per call) so the UI can show budget vs actual
  - `trajectoryVerdict`: last trajectory-eval outcome + the rule that failed, if any
  - `description`: new optional manifest field — one plain-English paragraph, distinct from `task` (one line). The AI authors it at unit birth (`ent new` prompts for it); the reconciler does not verify prose.
- `traces` already carry `{node, duration_ms, status, cost}` per hop — expose per-trace `id`, ordered hops, and total latency/cost so the UI can play them back. No new capture needed; this is plumbing.

### H0.2 Diff capture in the edit loop
- `apply_edit` records, per steering result: files touched, a unified diff per file
  (claims-scoped, so bounded), and the tier0 verdict before/after.
- Stored in `entiendo/steering/results/<id>.json` beside the existing outcome —
  human-readable, boring, inspectable.
- **Behaviour diff:** when golden fixtures exist, run them pre- and post-edit and
  include the metric delta in the result. This is the spec §6 "before/after
  behaviour diff", finally real.

### H0.3 Approval, for real
- New files: `entiendo/steering/proposals/<id>.json` — an edit to a unit with
  `approval.required: true` lands as a proposal (diff + behaviour delta + verdict),
  **not** applied to the working tree (agent works in a scratch copy of claims,
  or stashes — pick the boring one: apply, capture diff, `git stash`; approve =
  `stash pop` equivalent via stored diff apply).
- New endpoints: `GET /api/proposals`, `POST /api/proposals/<id>/approve`,
  `POST /api/proposals/<id>/reject`.
- MCP: `post_verdict` gains a `proposal: true` path so the operator skill routes
  gated units into proposals automatically.

**Acceptance:** `build_view()` on refundly shows interior + budgets + measured
latency for the decide unit; steering result JSON contains a real diff; a unit
with `approval.required: true` produces a proposal that approve applies and
reject discards, with history events for both. All existing tests green.

---

## Phase H1 — Refundly to full strength (½–1 day) **[reference data]**

Grow `examples/refundly` to the pipeline the v3 plan promised:

```
parse_email (compute) → orders (state) → policy (config)
        → decide (agentic: interior tools, trajectory) 
        → gateway.execute_refund (external, sideEffects: irreversible, approval.required: true)
        → ledger (state, writes)
```

- Six units, every node kind represented, one approval gate, one irreversible
  side effect, traces recorded for at least three synthetic requests (so Flow,
  Trace, and cost-vs-budget all have data).
- Budgets declared on decide + gateway with one deliberately blown budget
  (so the cost overlay has something amber to show).

**Acceptance:** `ent extract --check` reconciles at 100% coverage; `ent eval`
green except the blown budget; the recorded traces exercise every edge.
This repo becomes the fixture every H2–H5 acceptance runs against.

---

## Phase H2 — Design system + Universe shell rebuild (2–3 days)

### H2.1 The design brief (build to this, not around it)

**Subject:** celestial cartography — the product is literally called the
Universe; the design should commit to it. Not a dashboard: a **star chart you
operate**. Think engraved astronomical plates, observatory instruments,
annotated orbits — precise, calm, slightly antique instrumentation over a deep
field. This is the identity "mission control" claims and the current indigo
default doesn't earn.

**Tokens:**
- Palette: `--field #080B14` (deep ink, near-black blue), `--starlight #F2EFE6`
  (warm ivory ink — text), `--hairline #2A3244` (constellation lines),
  `--annotation #C9A961` (plate-gold: external units, approval gates, callouts),
  `--signal-green #3FBF7F`, `--signal-amber #E0A83C`, `--signal-red #E05252`
  (instrument signals, only ever meaning health).
- Type: display = **Fraunces** (a serif on a control surface is the deliberate
  risk — used only for the system name, group names, and dossier unit names);
  body/UI = **Inter**; data = **IBM Plex Mono** (hashes, invariants, diffs).
  Type scale: 28/17/13.5/11.5 with real hierarchy — no more everything-at-12px.
- **Signature element: the orbital interior.** An agentic unit is a body with
  its tools drawn as small satellites on an orbit ring inside its glow; each
  satellite's tether crosses the border to the edge it's declared against.
  The feature *is* the aesthetic. Spend the boldness here; keep everything
  else quiet hairlines and ivory type.

### H2.2 The shell
- **Zoom + pan** (wheel/pinch/drag-space), world coordinates, minimap when
  zoomed past 1.5×.
- **Touch:** pointer events replace mouse events throughout; tap = select,
  drag = move, pinch = zoom.
- **Search/jump** (`/` to focus): fuzzy match on id/name/task; selecting
  flies the camera to the unit and opens the dossier.
- **Keyboard:** tab cycles units, enter opens dossier, esc closes, arrows pan.
  Visible focus ring on canvas selection.
- **Groups collapse both ways:** click container to expand, dedicated control
  (and double-click background of group hull) to re-collapse; state kept.
- **URL state:** `#unit=refundly.decide&lens=health` — every view linkable.
- Reduced-motion: keep (already present), extend to camera flights.

**Acceptance:** refundly (6 units) and the 50-node synthetic fixture both
navigable by mouse, touch, and keyboard; >30 FPS at 50 nodes; deep link opens
directly on a selected unit with the right lens; screenshot review against the
brief (no regression to default-dashboard look).

---

## Phase H3 — Real lenses (2–3 days)

Each lens becomes a genuinely different view, not a recolour. Every lens still
terminates in an action (v3 risk rule stands).

- **Flow:** edge thickness = traffic volume; particle density from real hop
  counts; per-edge kind labels on hover.
- **Trace:** a trace picker (list of recorded requests with total latency +
  cost); selecting one **plays it back** — a comet travels hop by hop, each hop
  annotated with latency and status; failed hop halts the comet and pulses red.
  Scrub bar to step through hops. This is spec lens 3, five phases late.
- **Timeline:** a horizontal scrubber under the field; dragging it moves ALL
  units to their fingerprint at that commit — health colours and version bands
  update as you scrub. Per-unit: dossier timeline becomes clickable ticks with
  dimension chips (already computed by `_annotate_fingerprint_deltas`).
  Action: "replay against this fingerprint" wired to `ent replay`.
- **Health + cost:** cost overlay lands — units with budgets show a thin
  budget-burn arc (measured/budget) around the body; blown budget = amber arc
  regardless of eval verdict. Legend explains: correctness AND spend are health.
- **Blast radius:** keep, add rank labels from `blast_radius()` coupling scores.

**Acceptance:** on refundly, playing back a recorded trace visits every hop
with real latencies; scrubbing the timeline across the H1 commits visibly
changes at least one unit's fingerprint band; the blown budget renders amber;
each lens's action button does what it says.

---

## Phase H4 — Interiors rendered (1–2 days) **[the gap that started this]**

- Agentic units draw the orbital interior (signature element): satellites =
  registry tools, tether to the crossed edge, orbit ring dashed if
  `registryOnly` is not enforced at runtime.
- Dossier for agentic units gains an **Interior** section: the `process` prose,
  the tool registry with crossing targets, `maxSteps`, and the last trajectory
  verdict — including *which rule failed* on RED (from H0.1).
- Trace playback (H3) descends into interiors: hops attributed to a tool
  animate the satellite, so you watch the agent's actual path — and see it
  violate ordering when it does.
- Non-engineer reading: dossier order becomes description → task → verdict →
  interior → contract → fingerprint → edges → artifacts. Plain words first,
  hashes last, behind their headings.

**Acceptance:** refundly.decide renders order_lookup and issue_refund as
satellites tethered to orders and gateway; a trajectory-RED run names the
violated rule in the dossier; the recorded bad-order trace visibly animates
issue_refund before order_lookup.

---

## Phase H5 — Steer with eyes: diff-first review + approve (1–2 days)

- Steer result panel shows the **diff** (from H0.2): per-file unified diff in
  Plex Mono, additions/deletions coloured, collapsed per file; behaviour delta
  (golden metric before → after, with significance verdict) above it.
- Verdict, blast count, and diff live together: *what changed, what it did to
  behaviour, what's downstream* — the full trust story in one panel.
- Approval flow: units with the gate show proposals in the dossier
  (queued/awaiting states); **Approve** and **Reject** call the real H0.3
  endpoints; the gold gate arc pulses while a proposal waits.
- Empty states + errors written per interface-writing rules: every failure
  says what happened and what to do next; an empty universe invites `ent init`.

**Acceptance (the v4 demo):** open the Universe → click decide → steer "also
check the order is under 90 days old" → operator edits → dossier shows the
diff + behaviour delta + GREEN → click gateway (gated) → steer → proposal
appears with diff → Approve applies it, Reject discards, history records
both — all without a terminal after session start.

---

## Explicitly out of scope (v5 candidates)
- WebGL renderer (Canvas 2D + group-collapse holds to ~150 visible; revisit only when it hurts)
- SSE push for steering (polling stands at solo scale)
- Presence / multiplayer
- Retrofit UX beyond the existing skill
- Schema `apiVersion` bump (renames stay compat-aliased)

## Risks
| Risk | Mitigation |
|---|---|
| Design rebuild swallows the schedule | H2.1 brief is fixed before code; one signature element, everything else hairlines; screenshot self-review per phase |
| Diff capture races the working tree | Diffs computed inside the edit loop's existing claim-scoped apply; proposals use stored-diff apply, never live-tree magic |
| Timeline scrub is slow (re-checkout per tick) | Precompute fingerprint-per-commit into the history store at extract time; scrub reads, never checks out |
| Trace playback with no traces = dead lens | H1 ships recorded traces in the fixture; empty state links to `@ent.node` docs |
| Lens scope creep | v3 rule stands: a lens with no lever gets cut |

## Execution with Claude Code
One PR per phase, branch `v4/<phase>`. H0 → H1 strictly first; H2–H5 in order
(each builds on the last's surface). Kickoff prompt pattern unchanged from v3:
"Implement Phase H<X> of PLAN_v4.md. Read SPEC.md, LEXICON.md, and the design
brief in H2.1 first. All existing tests stay green; add the tests named in
acceptance; update docs in the same PR."

**Total: ~8–12 working days to a Universe that non-engineers can read,
trust, and steer — with the backend finally telling it everything it knows.**
