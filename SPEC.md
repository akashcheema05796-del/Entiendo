# Entiendo — Specification v3

> **Entiendo is the control plane for AI-built software.** Manifests hold the
> declared desired state (units, contracts, edges); a reconciler continuously
> verifies reality against it; evals are the health probes; fingerprints are the
> versioned identities; and the Universe is the surface through which humans
> steer and agents edit. **Human = operator, coding agent = workload, Entiendo =
> control plane.** It is *not* a visualization layer (it defines the truth, not
> just renders it) and *not* an IDE (humans never manipulate text here). It works
> *with* your IDE and your agent — it is the plane they operate under.

**The law (v3's one axiom).** A boundary is a valid **Logical Unit** *iff it can
be evaluated independently on given data* — from its own artifacts plus its
neighbours' contracts, never their interiors. Not evaluable alone → not a unit →
boundary error. This single test decides every boundary in the system.

> **Instrumentation at build time, not forensics after breakage.** Sensors go in
> while you build, so "which part broke" is already answered when something turns
> red. Entiendo is a read-only observer — never in the request path.

**Vocabulary.** v3 speaks of **units** (v2: nodes), **fingerprints** (v2:
versions), and **reflex / golden / judge** evals (v2: tier0 / tier1 / tier2). The
full glossary is **[LEXICON.md](./LEXICON.md)**; the roadmap is
**[PLAN_v3.md](./PLAN_v3.md)**. The *format* is unchanged — manifest filename,
`claims:` key, and `apiVersion: entiendo/v1` all stay (see LEXICON → Compatibility).

### Why the unit, not the file

Five independent lines of reasoning converge on the same primitive:

1. **Files are a human-production artifact.** Directory trees optimize for a
   person typing and remembering — not for how behaviour decomposes. When the
   agent writes the code, that ergonomic constraint is gone: the unit of *change*
   should be the unit of *behaviour*.
2. **LLM context economics.** An agent that swallows the whole repo to make one
   change pays for irrelevance in tokens, latency, and blast radius. A unit —
   claims plus neighbours' contracts — is the minimal correct retrieval set.
3. **Verification beats review.** Reading a diff tells you it *looks* right;
   re-running the unit's evals tells you it *is* right. The unit is the smallest
   thing you can independently re-verify — which is exactly the law.
4. **Fingerprint dimensionality.** Behaviour moves along code, prompt, config,
   and model. A file hash sees one dimension; a unit's composite fingerprint sees
   all four, so "what moved" has an answer.
5. **Precedent: RTL → netlist.** Hardware crossed this bridge decades ago — you
   describe intent (RTL) and a tool compiles and *verifies* it against a
   contract; nobody hand-places transistors. AI-built software is making the same
   move, and the verified unit is its netlist cell.

**Name note:** *entiendo* is Spanish for "I understand" (first person). The whole
claim of the tool is that the human *and* the model can say "I understand this
system." CLI binary: `ent`.

---

## 0. Scope

**What this is:** a build-time instrumentation layer + a generated system map + a scoped editing loop.

**What this is NOT:**
- Not an APM / trace viewer (those are run-centric; this is artifact-centric — executions are one *tab* on a node, not the primary object).
- Not a diagramming tool. Nothing here is hand-drawn.
- Not in the request path. Ever. See Invariant #2.

**Target:** greenfield projects first. Retrofit is explicitly v2 (see §12).

---

## 1. The core primitive: the Node

Everything in Entiendo hangs off one schema. If this file is right, the rest follows. If it's awkward, the whole system wobbles.

### 1.1 Node kinds

| Kind | Meaning | Drawn as |
|---|---|---|
| `compute` | Runs logic. Deterministic code, LLM call, agent, tool. | Solid box |
| `state` | Holds data. DB table group, vector index, cache, ledger file. | Cylinder |
| `schema` | A versioned data shape + its migration history. | Cylinder w/ version band |
| `config` | Environment/config surface. Secrets referenced, never rendered. | Dashed box |
| `external` | Third-party API you don't control. | Box w/ dashed border |
| `pipeline` | Composite — a group of nodes with its own end-to-end contract. | Container |

### 1.2 Manifest schema (`entiendo.node.yaml`)

```yaml
apiVersion: entiendo/v1
kind: Node

id: retrieval.chunk_ranker          # stable, globally unique, never renamed silently
name: Chunk Ranker
nodeKind: compute                   # compute | state | schema | config | external | pipeline
group: retrieval                    # hierarchy, for collapse/expand at scale
owner: mehar                        # human accountable, not the AI
status: active                      # active | deprecated | experimental

# ---- what this node owns. Drives the coverage metric. ----
claims:
  - src/retrieval/ranker.py
  - prompts/rank_v3.md
  - config/ranker.defaults.yaml

# ---- version = content hash of everything that can change behavior ----
version:
  code: <git sha of claimed source paths>
  prompt: <sha256 of claimed prompt files>
  config: <sha256 of resolved non-secret config>
  model: claude-sonnet-4-6          # model identity IS a version dimension
  composite: <hash of the above>    # this is what you pin, diff, and revert

# ---- the contract: what "correct" means for THIS node alone ----
contract:
  input:  { $ref: ./schemas/rank_request.json }
  output: { $ref: ./schemas/rank_response.json }
  invariants:
    - "len(output.chunks) <= input.k"
    - "all(c.score >= 0 for c in output.chunks)"
  sideEffects: none                 # none | writes | external | irreversible

# ---- edges. Extractor VERIFIES these against reality; it does not trust them. ----
dependencies:
  calls:  [retrieval.vector_store, llm.gateway]
  reads:  [state.doc_index]
  writes: []
  config: [config.retrieval]

# ---- tiered evals. Cost-aware by design. ----
evals:
  tier0:                            # deterministic, <1s, runs on EVERY edit
    - type: schema_validation
    - type: invariant_check
    - type: smoke
      fixture: evals/ranker/smoke.jsonl
  tier1:                            # golden dataset, runs pre-merge
    - type: golden
      dataset: evals/ranker/golden_v2.jsonl
      humanBlessed: true            # see §5.2 — AI may not author this alone
      metric: ndcg@5
      baseline: 0.81
      minRuns: 5                    # non-determinism: never judge on one run
      significance: 0.03            # below this delta = noise, not regression
  tier2:                            # expensive LLM-judge, nightly / on demand
    - type: llm_judge
      rubric: evals/ranker/rubric.md
      sampleSize: 50

# ---- budgets are health signals, same as correctness ----
budgets:
  p95LatencyMs: 800
  costPerCallUsd: 0.004
  tokensPerCall: 3500

observability:
  spanName: retrieval.chunk_ranker  # binds runtime traces back to this node

# ---- human gate ----
approval:
  required: false                   # true = edits to this node need human sign-off before merge
```

### 1.3 Repo layout

```
/entiendo/
  graph.json            # GENERATED. Never hand-edited.
  coverage.json         # GENERATED. Claimed vs unclaimed files.
  baselines/            # eval baselines per node version
  history/              # append-only node version + eval event log
/src/...
  <each module>/entiendo.node.yaml
/evals/
  <node-id>/golden_*.jsonl, rubric.md
```

---

## 2. Invariants (non-negotiable)

1. **The map is generated, never drawn.** Any hand-maintained diagram rots. If it can't be derived from the running system + manifests, it doesn't ship.
2. **Entiendo is a read-only observer.** It is never in the request path. If the extractor dies, production is unaffected.
3. **No node without a contract. No contract without a tier-0 eval.** A sensor that only emits data is noise. A sensor with a definition of "good" is signal.
4. **Every file is claimed by exactly one node — or explicitly listed as unclaimed.** Unclaimed is *visible*, not hidden. Coverage is a headline number.
5. **Manifests are verified, not trusted.** The extractor reconciles declared dependencies against actual imports/calls/spans. Divergence is a build failure, not a warning. *(This is the real anti-drift mechanism.)*
6. **Secrets are never rendered.** Only the fact of change and its timestamp.
7. **Health is judged against a baseline with a significance threshold**, never a raw score. Otherwise the map flickers and people stop opening it.
8. **The AI edits through the node, not through the repo.**

---

## 3. Layered architecture

Strictly separable. Each layer testable alone. Build in order.

```
L0  Manifest & schema layer      — declaration + validation
L1  Extractor / reconciler       — emits graph.json + coverage.json; fails on drift
L2  Instrumentation              — OTel spans tagged with node_id; eval runner; cost meter
L3  History store                — append-only versions + eval results + traces
L4  Render surface               — one topology, six lenses
L5  Scoped edit loop             — node → AI context → edit → eval → verdict
```

**L2 detail — trace binding.** A decorator/middleware (`@ent.node("retrieval.chunk_ranker")`) emits OpenTelemetry spans with `entiendo.node_id` as an attribute. Without this, the flow and trace lenses cannot exist. It is the single piece of code that must be in the app.

**L3 detail — storage split:**
- Node versions & manifests → git (content-addressed, free history)
- Eval results & budgets → time-series (DuckDB/Parquet is enough to start)
- Traces → span store (OTel-compatible), sampled
- Graph snapshots → `graph.json` per commit

---

## 4. The lenses — one topology, six views

Same boxes every time. Only the meaning of colour and motion changes. This is what makes it *control*, not three dashboards you cross-reference in your head.

| # | Lens | Question it answers | Colour/motion means |
|---|---|---|---|
| 1 | **Structure** | What is this system? | Node kind + group |
| 2 | **Flow** | How does data move? | Edge direction, volume |
| 3 | **Trace** | What happened to *this* request? | Live animation along edges, latency per hop |
| 4 | **Health** | Is it okay right now? | Eval verdict + budget burn (green / degraded / red) |
| 5 | **Timeline** | What changed, and when? | Scrub a node backward through composite versions; schema migrations and config changes appear on the same axis as code |
| 6 | **Blast radius** | What breaks if I touch this? | Select node → downstream dependents highlighted, ranked by contract coupling |

**Added since v1:** lens 6 (blast radius — turns health from reactive to preventive) and **cost** as a first-class overlay on lens 4, because for LLM-heavy systems spend *is* health.

**Scale rule.** 500 nodes is unreadable. Rendering collapses by `group` by default; you expand into a group. Hierarchy is a manifest field, not a UI afterthought.

**Presence (optional, team mode).** Who is editing where, right now. Only matters once more than one person is in the repo — defer past MVP.

---

## 5. Evals — the part that decides if this is real

### 5.1 Tiering is a cost decision
Running LLM-judge evals on every keystroke is financially absurd. Hence:
- **tier0** on every edit (deterministic, sub-second, free)
- **tier1** pre-merge (golden datasets, bounded cost)
- **tier2** nightly or on demand (LLM judge, expensive)

### 5.2 The bootstrapping trap
If the AI writes both the code and the test that grades the code, you have a tautology, not a signal. Rule:
- The AI may author **tier0** freely (schema/invariant/smoke — mechanical).
- **tier1 golden datasets require `humanBlessed: true`.** A human approves the expected outputs at least once. The AI may *propose* rows; it may not bless them.
- **tier2 rubrics** are human-authored, AI-refined.

### 5.3 Non-determinism
A node scores 0.87. Was it 0.89 yesterday? That is noise, not a regression. Every tier1 eval declares `minRuns` and `significance`. The health lens shows **red only on statistically meaningful movement**. Everything else is "within band."

### 5.4 Node-level revert
Because a node version is a *composite* hash (code + prompt + config + model), you can pin and revert one node without touching anything else — and replay yesterday's inputs against today's version to see exactly what moved. Without these two capabilities the whole tool is decoration.

---

## 6. The scoped edit loop (L5)

```
1. Human clicks node on the map.
2. Entiendo assembles the AI context window:
     - this node's manifest (contract, deps, budgets)
     - this node's claimed files
     - the CONTRACTS ONLY of immediate neighbours (not their bodies)
     - the last N eval results + current baseline
   → everything else in the repo is excluded by construction.
3. Human talks. AI edits within claimed files only.
   Touching a file outside `claims` requires an explicit boundary-change proposal.
4. tier0 evals rerun automatically. Verdict in seconds.
5. Blast-radius lens shows what downstream is now at risk.
6. If `approval.required: true` → change surfaces as a proposal on the node,
   with a before/after behaviour diff, awaiting human sign-off.
7. On merge: tier1 runs. Baseline updated only on human confirmation.
```

**Why this matters beyond ergonomics:** today an AI edit swallows the whole codebase and guesses what's relevant — slow, expensive, and exactly how unrelated things break. The manifest *is* the retrieval index. The map is the human's steering wheel and the model's map simultaneously. That dual purpose is the reason to build it properly rather than bolt a dashboard on afterward.

---

## 7. Gaps filled since v1

| # | Gap in v1 | Resolution |
|---|---|---|
| 1 | Nothing enforced manifest ↔ reality | Extractor **reconciles** and fails the build on divergence (Invariant 5) |
| 2 | Who writes the evals? | Tiered authorship + `humanBlessed` on golden sets (§5.2) |
| 3 | Eval cost ignored | tier0/1/2 split (§5.1) |
| 4 | Non-determinism unaddressed — flickering health | `minRuns` + `significance`; red only on meaningful movement (§5.3) |
| 5 | No trace→node binding | `@ent.node()` decorator emitting `entiendo.node_id` on OTel spans (§3, L2) |
| 6 | "Revert one component" claimed, never specified | Composite content hash per node; pin/revert/replay (§5.4) |
| 7 | Glue code invisible | `claims` + `coverage.json`; unclaimed files shown, not hidden (Invariant 4) |
| 8 | DB treated as generic state | `schema` node kind; migrations on the timeline axis beside code |
| 9 | Config/env not modelled — cause of ~half of prod breakage | `config` node kind, change-tracked, secrets never rendered |
| 10 | No preventive view | Blast-radius lens (lens 6) |
| 11 | Cost invisible | Budgets in manifest; cost overlay on health lens |
| 12 | Unreadable above ~100 nodes | `group` hierarchy + collapse/expand |
| 13 | No human approval gate — the original motivation | `approval.required` + change proposals on the node (§6, step 6) |
| 14 | Tool failure mode undefined | Read-only observer, never in request path (Invariant 2) |
| 15 | Model identity not versioned | `version.model` — swapping models changes behaviour and must diff |

---

## 8. Build order

Each phase ships something testable. Do not start a phase before the previous one's acceptance criteria pass.

### Phase 1 — L0: Boundaries
Manifest schema, JSON-Schema validator, `ent init`, `ent validate`.
**Acceptance:** a repo with 3 hand-written manifests validates; a malformed one fails with a useful error.

### Phase 2 — L1: Extractor & reconciler
Static analysis of claimed files → actual imports/calls. Emit `graph.json`, `coverage.json`. Fail on declared-vs-actual divergence.
**Acceptance:** deliberately add an undeclared dependency → build fails naming both nodes. Coverage number is correct.

### Phase 3 — L2: Instrumentation + eval runner
`@ent.node()` decorator, OTel span attribution, tier0 runner, cost meter.
**Acceptance:** one real request produces spans mapped to node IDs; `ent eval <node>` returns tier0 verdict in <2s.

### Phase 4 — L3/L4: History + render (lenses 1, 4, 5)
Append-only history store. Web surface: structure, health, timeline. **Ship these three first** — they deliver the "everything under control" glance.
**Acceptance:** a node's version change is visible on the timeline within one commit; health colour matches `ent eval` output.

### Phase 5 — L4 remainder: lenses 2, 3, 6
Flow, trace, blast radius.

### Phase 6 — L5: Scoped edit loop
Context assembler, claim-boundary enforcement, auto tier0 rerun, approval gates.
**Acceptance:** clicking a node and requesting a change produces an edit confined to `claims`, with a pass/fail verdict, without loading unrelated files.

---

## 9. MVP — the two-week slice

Resist building all six lenses. Prove the loop end to end on **five nodes** of one real project:

1. Manifest schema + validator
2. Extractor emitting `graph.json` (static only, no runtime yet)
3. tier0 eval runner
4. **One** rendered lens: health-coloured structure map
5. Click a node → see its manifest, version, last eval, claimed files

If that doesn't already feel useful, the full version won't either. Everything after is amplification, not rescue.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Manifest maintenance becomes a tax people route around | Reconciler failure must be *fast and specific*; AI authors the manifest as part of creating the node, never as a separate chore |
| Evals are cosmetic (AI grading itself) | `humanBlessed` gate on tier1 |
| Health map flickers → ignored by week three | Significance thresholds; "within band" is a first-class state |
| Becomes a viewer nobody opens | Every lens must terminate in an action: edit, revert, or approve. A lens with no lever gets cut |
| Map itself leaks architecture/secrets | Read-only, auth-gated, secrets by reference only |
| Solo-builder scope explosion | Ship §9 first. Team/presence features deferred indefinitely |

---

## 11. Greenfield vs retrofit

**Greenfield-first — deliberate, not incidental.** Every node registers its manifest at birth, so the map is never wrong and coverage is 100% from line one. The discipline is cheap when it's the default and expensive when it's remedial.

**Retrofit is a genuinely harder engineering problem, flagged v2.** The extractor must *infer* boundaries nobody declared, and it will guess wrong often. The likely v2 path is AI-proposed manifests from an existing repo, reviewed node by node by a human — a semi-automated migration, not a scan. Starting there will drown the project.

---

## 12. Notes for Claude Code

- Build L0→L5 in strict order. Do not begin the render surface before the reconciler passes.
- `graph.json` and `coverage.json` are **generated artifacts** — never hand-edit, never commit conflicts into them.
- Language/stack: pick one runtime for the instrumentation decorator first (Python suggested, given the target project), and treat multi-language extraction as a later concern.
- The manifest schema is the contract for the entire system. Change it only deliberately and version it (`apiVersion: entiendo/v1`).
- Prefer boring, inspectable storage (Parquet/DuckDB, JSON, git) over a database service. The tool must be trivially recoverable.

---

## 13. Boundary stress cases — the law, applied

The law ("evaluable alone → unit") resolves the cases where directory grouping
guesses wrong. Test every proposed boundary against it:

- **A RAG bot as one file.** `bot.py` parses the query, retrieves, ranks, calls
  the LLM, and formats. One file, but *not* one unit: you cannot evaluate
  "ranking" without also exercising retrieval and generation. Split until each
  piece has a contract you can grade on given data — ranker (chunks → order),
  retriever (query → chunks), generator (context → answer).
- **A prompt + its renderer + its defaults, across three directories.** One
  behaviour smeared across the tree. It *is* one unit: the claims are "everything
  that can change this behaviour," which is also what the fingerprint hashes.
  Merge them.
- **Two responsibilities in one directory** (auth + rate-limiting in
  `middleware/`). Two units: each is independently evaluable, so the directory is
  the wrong seam.
- **A pure DTO / schema with no behaviour.** Evaluable only as a shape → a
  `schema` unit whose contract is the shape + its migrations, not a `compute`.
- **Untestable glue** (a 5-line adapter with no defensible "correct"). Not a unit
  — leave it explicitly *unclaimed* (Invariant 4). Unclaimed is visible, not a
  failure; it is the finding "this glue has no contract."

---

## 14. Agentic units — interiors, tools, trajectory contracts

A `compute` unit whose interior is an agent (a multi-step loop that chooses
tools) needs more than an input/output contract: the *path* matters, and the path
can be wrong even when the answer is right.

### 14.1 The interior block

```yaml
interior:
  process: >                      # human-readable description of the loop
    Classify intent, look up the order, decide, then act.
  tools:                          # the ONLY tools this unit may call
    - name: order_lookup
      crosses: retrieval.orders   # the edge this tool traverses (reconciled!)
    - name: issue_refund
      crosses: payments.gateway
  maxSteps: 8
```

### 14.2 Trajectory invariants (a reflex-tier eval)

```yaml
evals:
  tier0:
    - type: trajectory
      order: [order_lookup_before_issue_refund]   # a must precede b
      maxSteps: 8
      registryOnly: true                           # no tool outside interior.tools
```

Evaluated against recorded spans or a run-log fixture (JSONL of tool calls) —
deterministic, <1s. A right answer reached by a forbidden order is **RED**.

### 14.3 Reconciled tools

Every `interior.tools[].crosses` must have a matching declared edge. A tool that
crosses a border with no edge is drift — `ent extract --check` fails, naming the
unit and the tool. Runtime guard: `ent.guard(registry)` raises on an
out-of-registry call, so the border holds in production too (still read-only — it
guards the workload, it is not the workload).

---

## 15. Competitive positioning — verified spec-driven development

Spec-driven development (Spec Kit, Kiro, Tessl) turns a written spec into code.
Entiendo's difference is one word: **verified**. A spec is a promise; a unit is a
promise *plus a continuously-checked proof* (its evals) *plus a reconciler* that
fails the build when code drifts from the declaration. The others generate and
trust; Entiendo generates and **verifies**, forever, as a control loop.

| | Spec-driven tools | Entiendo |
|---|---|---|
| Artifact | a spec that produces code | a unit: contract + evals + fingerprint |
| After generation | spec and code drift silently | reconciler fails the build on drift |
| "Correct" means | matches the prose | passes the health probes on given data |
| Human role | author the spec | operate the plane (steer / approve / bless) |
| Agent role | one-shot author | continuous workload under the plane |

Not an IDE (humans don't edit text here) and not a visualizer (it defines the
truth, not just renders it). It **works with** your IDE and your agent — it is
the plane they operate under.

---

## 16. Reference project — refundly

`examples/refundly/` is the v3 reference project: a support agent that parses an
email → looks up the order (retrieval) → reads policy (`config`) → **decides** (an
agentic unit with interior tools + trajectory invariants) → executes the refund
(`external`, `irreversible`, `approval.required: true`) → writes a case ledger
(`state`). It exercises every v3 feature — the law, agentic units, the approval
gate, and fingerprint replay — and grows phase by phase alongside the build, each
phase's acceptance running against it.
