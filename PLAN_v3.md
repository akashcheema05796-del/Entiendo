# Entiendo v3 — Implementation Plan
## "The control plane for AI-built software"

**Category statement (goes at the top of SPEC v3):**
Entiendo is not a visualization layer (it defines the truth, not just renders
it) and not an IDE (humans never manipulate text here). It is a **control
plane**: manifests hold the declared desired state (units, contracts, edges),
a reconciler continuously verifies reality against it, evals are the health
probes, fingerprints are the versioned identities, and the Universe is the
surface through which humans steer and agents edit. Human = operator,
coding agent = workload, Entiendo = control plane.

**The law (v3's one new axiom):**
A boundary is a valid Logical Unit **iff it can be evaluated independently on
given data** — its own artifacts plus neighbours' contracts, never their
interiors. Not evaluable alone → not a unit → boundary error.

**Already shipped — do not rebuild:** manifest schema & validation (L0),
extractor/reconciler with drift-as-build-failure (L1), instrumentation +
reflex/golden/judge runners (L2), history (L3), six lenses (L4), scoped edit
loop + `ent serve` (L5), retrofit staging, MCP server (9 tools), CI,
134 tests, retrofit skill, CLAUDE.md.

**Ordering principle:** moat before demo. B unlocks the eyes, C unlocks the
thesis, D–E are the defensible verification depth, F–G finish the language.

---

## Phase A — v3 documents (½ day)
Land the thinking so every later PR has a source of truth.

- `SPEC.md` v3 preamble: category statement, the law, the "logical
  explanation" argument (files = human-production units; LLM context economics;
  verification > review; fingerprint dimensionality; RTL/netlist precedent).
- `LEXICON.md` into repo root (from the drafted lexicon).
- SPEC sections: boundary stress cases (RAG-bot outliers), Agentic Units
  (interiors, tools, trajectory contracts), competitive positioning
  ("verified SDD" vs Spec Kit / Kiro / Tessl).
- README repositioned: hero = "steer your codebase like mission control",
  subhead = control plane category, "works with your IDE and your agent."

**Acceptance:** SPEC v3 answers "what is this" in its first ten lines; every
term used in SPEC exists in LEXICON; CI green (docs only).

---

## Phase B — Universe render (1–2 days)
Port the prototype (`entiendo-universe.html`) to be THE render surface.

- Replace `build_app_html()` output with the Universe: indigo field,
  kind-forms (orb / ringed / dashed / gold diamond), health glow + pulse,
  flow particles (verified = bright/fast, declared = dim/dashed),
  hover isolation, drag, blast-radius tint on select, dossier panel,
  lens toggles, reduced-motion support.
- **Logic-first dossier:** task + contract + verdict + fingerprint + edges;
  artifacts (claims) collapsed behind a disclosure. Every dossier ends in an
  action: steer / revert / approve.
- Data injected from `build_view()`; no fetch needed for static render;
  `ent serve` mode hydrates from `/api/graph`.
- Group-collapse: >12 units renders groups as container bodies; click to
  expand (manifest `group` field drives it).

**Acceptance:** `ent render` on examples/greenfield produces the Universe;
`ent serve` shows live verdicts after `ent eval`; 50-node synthetic fixture
stays readable (groups collapsed) and >30 FPS; existing render tests updated,
new DOM-structure tests for dossier fields.

---

## Phase C — The Bridge: canvas → Claude Code (2–3 days) **[thesis]**
Clicking "steer" in the browser must drive a live Claude Code session.

Design (boring, inspectable, no websockets to CC):
- `POST /api/steer {unit, instruction}` → appends JSON line to
  `entiendo/steering/queue.jsonl`; UI shows "queued".
- New MCP tools: `await_steering(timeout_s)` — long-polls the queue, returns
  next request; `post_verdict(request_id, outcome)` — writes result to
  `entiendo/steering/results/`, which `ent serve` streams to the UI (SSE or
  poll) so the bubble updates and the dossier shows the verdict.
- New skill `entiendo-operator`: instructs Claude Code to loop —
  await_steering → get_node_context → apply_edit → post_verdict — and to
  propose boundary changes instead of writing around claims.
- Session start: user runs `claude` in the repo and says "operate the map"
  (skill trigger), or `ent serve --operator` prints the exact command.

**Acceptance (the demo):** open Universe → click Chunk Ranker → type
"also weight recency" → Claude Code (running in terminal) picks it up, edits
within claims, reflex reruns → bubble flashes, dossier shows GREEN verdict —
zero terminal typing after session start. Queue/results files are
human-readable. Unit tests for queue append/consume + verdict post; skill
dry-run test with a scripted fake agent.

---

## Phase D — Trajectory invariants + registry (2 days) **[agentic units]**
- Manifest: `interior:` block — `process` (free text), `tools` registry,
  `maxSteps`; `evals.tier0` gains `type: trajectory` with rules:
  `order: [a_before_b, ...]`, `maxSteps`, `registryOnly: true`.
- Runner: reflex tier evaluates trajectory rules against recorded spans /
  a run log fixture (JSONL of tool calls) — deterministic, <1s.
- Reconciler: declared `interior.tools` that cross the border must have a
  matching edge; an edge-crossing tool with no edge = drift = build failure.
  Runtime guard helper: `ent.guard(registry)` raises on out-of-registry calls.

**Acceptance:** fixture where the right answer is produced via a forbidden
order → reflex RED; undeclared border-crossing tool → `ent extract --check`
fails naming unit and tool; greenfield example gains one agentic unit
demonstrating both.

---

## Phase E — Fingerprint replay (1–2 days) **[the Day-30 payoff]**
- `ent replay <unit> --against <fingerprint>`: check out the unit's claimed
  files + prompt + config at the old fingerprint (git + history store),
  run golden fixtures against old and current, print side-by-side metrics
  with significance verdict.
- `ent pin <unit> model=<id>` writes a pin into the manifest (fingerprint
  moves, visible on Timeline).
- Timeline lens: fingerprint dimension deltas (code/prompt/config/model)
  shown per version tick.

**Acceptance:** in the example repo, bump a model string, replay shows the
delta attributed to `model` only; pin restores; history records both events.

---

## Phase F — Unit birth + retrofit v2 (1–2 days) **[the law as a tool]**
- `ent new`: interactive — asks task (one sentence), kind, and THE question:
  "give one fixture → expected verdict". Refuses to scaffold without it;
  writes manifest + empty fixture file + reflex smoke.
- Retrofit skill update: proposals phrased as tasks; each proposal must
  include a candidate fixture→verdict or be marked `boundary-uncertain`.
- Delete `--accept-all` from `ent retrofit` (undermines blessing).

**Acceptance:** `ent new` cannot produce a unit without a fixture pair;
retrofit on the vibetest sample yields task-phrased proposals; `--accept-all`
gone, test updated.

---

## Phase G — Lexicon in the product (1 day)
- CLI/UI/docs say unit, fingerprint, reflex/golden/judge, steer, bless.
- Compatibility: `entiendo.node.yaml` filename, `claims:` key, and
  `apiVersion: entiendo/v1` unchanged (schema bump is a separate, deliberate
  v2 decision). CLI aliases: old command names keep working with a
  deprecation note.

**Acceptance:** grep of user-facing strings shows no bare "node" (except
compat notes); all 134+ tests green; help text uses the lexicon.

---

## Reference project
Add `examples/refundly/` (support agent: parse email → lookup order →
policy config → decide (agentic, interior tools) → execute refund
(external, irreversible, approval) → case ledger (state)). It exercises
every v3 feature: trajectory invariants, approval gate, replay, the law.
Grows phase by phase; each phase's acceptance runs against it.

## Execution with Claude Code
One PR per phase, branch `v3/<phase>`. Kickoff prompt pattern:
"Implement Phase <X> of PLAN_v3.md. Read SPEC.md and LEXICON.md first.
Follow CLAUDE.md invariants. All existing tests stay green; add tests named
in the acceptance criteria; update docs in the same PR. Show me the PR link."
Phases A+B can land in one PR; C is its own PR (the thesis deserves clean
review); D–G one each.

## Risks
- Bridge queue is polling, not push — acceptable at solo scale; SSE upgrade
  noted, not built.
- Rename fatigue: G touches many strings — do it last, mechanically.
- Refundly scope creep: it is a fixture, not a product; no real Stripe.
- Canvas performance beyond ~150 visible units: group-collapse is the
  answer; do not add WebGL until it hurts.

**Total: ~9–12 working days to a defensible, demoable control plane.**
