---
name: entiendo-retrofit
description: >
  Retrofit an existing (unmanaged) repository into Entiendo nodes. Use whenever
  the user asks to "retrofit", "map", "visualize", or "bring under Entiendo" a
  project that has no entiendo.node.yaml manifests, to review/improve staged
  retrofit proposals, or to run the semantic sweep ("green the gate", "add
  fixtures", "sweep the units") on a mapped repo. Replaces the
  directory-grouping heuristic with semantic boundary analysis: read the code,
  propose nodes with real contracts, author per-unit test sets, and walk the
  human through accepting them one by one.
---

# Entiendo Retrofit — Semantic Boundary Proposal

You are turning an unmanaged repo into a node graph. The built-in
`ent retrofit` heuristic groups files by directory — legible but often wrong.
Your job is to do better: read the code and propose boundaries that match how
the system actually behaves, then let the human accept node by node.

**The prime rule: this is a semi-automated migration, not a scan.** Nothing is
written into the real tree until the human accepts a proposal. Never bulk-accept.

## Workflow

1. **Baseline pass.** Run the `retrofit_propose` MCP tool (or `ent retrofit`).
   This stages heuristic proposals in `entiendo/proposals/` with confidence
   scores. Treat them as a draft, not an answer.

2. **Read before you regroup.** For each low-confidence or suspicious proposal,
   read the actual files. Look for the real seams:
   - a directory holding two unrelated responsibilities → split into two nodes
   - one behaviour smeared across directories (e.g. a prompt file + the code
     that renders it + its config) → merge into one node; a node's `claims` are
     "everything that can change this behaviour", which is also what feeds the
     composite version hash
   - LLM calls, DB access, external APIs → these mark node kind and edges

3. **Assign `nodeKind` by behaviour, not extension:**
   - `compute` — runs logic (deterministic code, LLM call, agent, tool)
   - `state` — holds data (tables, indexes, caches, ledger files)
   - `schema` — a versioned data shape + migrations
   - `config` — env/config surface; reference secrets, never render values
   - `external` — third-party API the team doesn't control
   - `pipeline` — a composite group with its own end-to-end contract

4. **Phrase every proposal as a task, with a fixture → verdict.** Each proposal
   gets a one-sentence **`task`** ("what is this unit for?") and a **candidate
   fixture → expected verdict** — one input and the output that would make it
   pass. A unit is only valid if it can be evaluated on given data (the law); if
   you cannot supply that pair, mark the proposal **boundary-uncertain** and say
   why. That is a finding, not a failure — never accept a boundary-uncertain
   proposal until a human supplies the fixture pair (`ent new` is the same gate
   for greenfield units).

5. **Every node gets a contract.** No node without a contract; no contract
   without a tier-0 eval (Invariant 3). At minimum: input/output shape (JSON
   Schema, even loose), one or two invariants you can defend from the code, and
   `sideEffects` (none | writes | external | irreversible).

6. **Declare dependencies you can point to.** `calls` / `reads` / `writes` /
   `config` edges must correspond to actual imports, calls, or I/O you saw.
   The extractor VERIFIES declarations against reality and fails the build on
   divergence (Invariant 5) — do not guess edges into existence.

7. **Propose evals with correct authorship:**
   - tier0 (schema/invariant/smoke) — you may author these freely; mechanical.
   - tier1 golden datasets — you may PROPOSE rows, but `humanBlessed: true`
     requires the human to approve expected outputs. Never set it yourself.
   - tier2 rubrics — draft only if asked; the human owns them.

8. **Present one node at a time.** For each: id, kind, claimed files, the
   contract in one or two sentences, edges with your evidence, and your
   confidence. Ask the human to accept, amend, or reject. On accept, call
   `retrofit_accept` for that id only.

9. **Finish with coverage.** Run `validate_manifests` and the extractor. Report
   the coverage number and list unclaimed files explicitly — unclaimed is
   visible, not hidden (Invariant 4). Ask whether the leftovers should become
   nodes, be acknowledged, or be flagged as glue debt.

## The semantic sweep — turning UNTESTED green

Once the map exists, the eval gate usually shows a wall of UNTESTED units.
This is the work the deterministic tool cannot do and you can: **read every
unit's code and author its test set.** Run it when the user asks to "green
the gate", "add fixtures", "sweep the units", or after finishing a retrofit.

Per unit, in importance order (blast radius, then real logic over glue):

1. **Probe first, guess never.** Try importing each claimed file the way the
   eval loader would. Three outcomes: a *pure importable core*, a *missing
   runtime* (rosbag outside ROS), or *no runnable code* (data/config).
2. **Pure core → author the fixture set.** Pick the entrypoint that holds the
   real logic (a parsing/decision function, not the CLI shim). Write rows
   covering: one typical case, one boundary (the 40-vs-41 bin edge, the
   commented-out line that must NOT match), one error path (`expectError`).
   Multi-argument or class-based? Write a harness under `evals/<unit-id>/`
   — test scaffolding, never claimed. Then **execute before you stage**:
   `ent eval <unit>` must pass before the fixture is real. A row that fails
   is telling you your reading of the code is wrong — investigate it, never
   force the expectation to match.
3. **Say where every expectation came from.** A value you derived by reading
   the code/docs is *contract-derivable*; a value you copied from running
   the code is *implementation-derived* — it pins today's behaviour
   (regression netting, legitimate tier0) but is not ground truth. Mark
   which, and never bless either yourself.
4. **Missing runtime → declare it.** `contract.requires: [rosbag]` where the
   schema supports it (≥0.3) so the unit reads ENV-BLOCKED; on older
   schemas, `evals.executionMode: skip` with a comment naming the runtime.
   Never leave a wrong-environment ERROR standing — it drowns real defects.
5. **Config/data → interior is honest.** Don't force fixtures onto pure
   data units; grey-by-design beats a fake smoke test. If a schema exists,
   a `schema_validation` contract is the right upgrade.
6. **Close the loop visibly.** Re-run `ent ci` as you go; finish by
   reporting the before/after eval line ("0 green, 38 untested, 5 error →
   8 green, 35 untested, 0 error") — the sweep's deliverable is that diff.

Hard limits, same as everywhere: tier1 golden rows may be *proposed*, only a
human blesses; never redraw an accepted boundary mid-sweep without sign-off;
if `ent ci --enqueue-failures` queued steering tasks, work through those via
`await_steering`/`post_verdict` rather than around them.

## Naming and hygiene

- `id` is stable, dotted, never silently renamed: `<group>.<name>`
  (e.g. `retrieval.chunk_ranker`). Set `group` — the map collapses by it.
- `owner` is the human accountable, never the AI.
- New/uncertain nodes start `status: experimental`.
- Nodes with `sideEffects: irreversible` or writes to shared state should get
  `approval.required: true` by default; let the human relax it.

## Anti-patterns

- One giant node claiming half the repo (defeats scoped editing).
- One node per file (noise; nodes are behaviours, not files).
- Edges declared "to be safe" (the reconciler will fail the build).
- Blessing your own golden data (tautology, not signal — §5.2 of the spec).
- Accepting proposals on the human's behalf, ever.
