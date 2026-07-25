---
name: entiendo-retrofit
description: >
  Retrofit an existing (unmanaged) repository into Entiendo nodes. Use whenever
  the user asks to "retrofit", "map", "visualize", or "bring under Entiendo" a
  project that has no entiendo.node.yaml manifests, or to review/improve staged
  retrofit proposals. Replaces the directory-grouping heuristic with semantic
  boundary analysis: read the code, propose nodes with real contracts, and walk
  the human through accepting them one by one.
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

4. **Every node gets a contract.** No node without a contract; no contract
   without a tier-0 eval (Invariant 3). At minimum: input/output shape (JSON
   Schema, even loose), one or two invariants you can defend from the code, and
   `sideEffects` (none | writes | external | irreversible). If you cannot state
   what "correct" means for a node, say so — that is a finding, not a failure.

5. **Declare dependencies you can point to.** `calls` / `reads` / `writes` /
   `config` edges must correspond to actual imports, calls, or I/O you saw.
   The extractor VERIFIES declarations against reality and fails the build on
   divergence (Invariant 5) — do not guess edges into existence.

6. **Propose evals with correct authorship:**
   - tier0 (schema/invariant/smoke) — you may author these freely; mechanical.
   - tier1 golden datasets — you may PROPOSE rows, but `humanBlessed: true`
     requires the human to approve expected outputs. Never set it yourself.
   - tier2 rubrics — draft only if asked; the human owns them.

7. **Present one node at a time.** For each: id, kind, claimed files, the
   contract in one or two sentences, edges with your evidence, and your
   confidence. Ask the human to accept, amend, or reject. On accept, call
   `retrofit_accept` for that id only.

8. **Finish with coverage.** Run `validate_manifests` and the extractor. Report
   the coverage number and list unclaimed files explicitly — unclaimed is
   visible, not hidden (Invariant 4). Ask whether the leftovers should become
   nodes, be acknowledged, or be flagged as glue debt.

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
