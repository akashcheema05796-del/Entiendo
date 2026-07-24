# Build order

From SPEC.md §8. Each phase ships something testable. **Do not start a phase
before the previous one's acceptance criteria pass.** This file tracks status.

Legend: ☐ not started · ◐ in progress · ☑ done

| Phase | Layer | Status |
|---|---|---|
| 1 | L0 — Boundaries | ☑ `ent validate` + `ent init` working |
| 2 | L1 — Extractor & reconciler | ☑ `ent extract` → graph.json + coverage.json |
| 3 | L2 — Instrumentation + eval runner | ☑ `@ent.node()` spans + `ent eval` tier0 |
| 4 | L3/L4 — History + render (lenses 1, 4, 5) | ☑ `ent snapshot` + `ent render` |
| 5 | L4 — remainder (lenses 2, 3, 6) | ☑ flow / trace / blast radius |
| 6 | L5 — Scoped edit loop | ☐ |

---

## Phase 1 — L0: Boundaries
Manifest schema, JSON-Schema validator, `ent init`, `ent validate`.

**Acceptance:** a repo with 3 hand-written manifests validates; a malformed one
fails with a useful error. ✓ **Met** — `ent validate` validates the five
greenfield manifests and reports specific, per-field errors on malformed input;
`tests/test_validation.py` covers both directions.

Implemented:
- `src/ent/schema.py` — cached schema load + Draft 2020-12 validator
- `src/ent/manifest.py` — `discover()`, `load()`, `Node` model
- `src/ent/validation.py` — schema conformance + semantic rules (id uniqueness,
  `$ref` resolution, claim existence, `humanBlessed` gate)
- `src/ent/commands/validate.py` — one-pass report, exit 0/1/2
- `src/ent/commands/init.py` — idempotent `entiendo/` scaffold + starter manifest

## Phase 2 — L1: Extractor & reconciler
Static analysis of claimed files → actual imports/calls. Emit `graph.json`,
`coverage.json`. Fail on declared-vs-actual divergence.

**Acceptance:** deliberately add an undeclared dependency → build fails naming
both nodes. Coverage number is correct. ✓ **Met** — `ent extract` verifies
Python import edges against declared `dependencies`; an undeclared edge fails
naming both nodes; the greenfield example reconciles clean at 100% coverage.
`tests/test_extractor.py` covers drift, double-claim, dangling deps, coverage.

Implemented:
- `src/ent/extractor.py` — AST import analysis, edge reconciliation (undeclared
  = hard fail; declared-but-unverified = reported), coverage over the file
  universe with an `entiendo/unclaimed.txt` acknowledgement list, deterministic
  `graph.json` + `coverage.json` output
- `src/ent/commands/extract.py` — validates first, writes artifacts (or `--check`
  CI mode), exit 0/1/2
- greenfield: `ranker.py` now imports its neighbours (verified edges) and
  `entiendo/unclaimed.txt` acknowledges IO schemas / eval fixtures / docs

Note: `graph.json` / `coverage.json` are generated (git-ignored in the example);
run `ent extract` to regenerate them.

## Phase 3 — L2: Instrumentation + eval runner
`@ent.node()` decorator, OTel span attribution, tier0 runner, cost meter.

**Acceptance:** one real request produces spans mapped to node IDs;
`ent eval <node>` returns tier0 verdict in <2s. ✓ **Met** — a call through an
`@ent.node()` callable produces a span carrying `entiendo.node_id` (verified via
`ent.tracing.capture()`); all five greenfield nodes return a green tier0 verdict
in well under 2s (~1–70ms each). `tests/test_instrument.py` + `tests/test_evals.py`.

Implemented:
- `src/ent/tracing.py` — OTel-compatible `Span` + opt-in `capture()` recorder;
  emits a real OTel span when opentelemetry is installed, no-op otherwise. Never
  in the request path (Invariant 2).
- `src/ent/instrument.py` — real `@ent.node()` (times, re-raises unchanged, binds
  `entiendo.node_id`) + `ent.record()` cost/token meter.
- `src/ent/evals/runner.py` — deterministic tier0: schema_validation,
  invariant_check, smoke → green/red verdict.
- `src/ent/commands/eval.py` — `ent eval <node>`; tier0 now, tier1/tier2 announced.

Note: runtime invariant *enforcement* and tier1/tier2 (golden/LLM-judge) are
deliberately deferred — tier0 stays static so it's deterministic and sub-second.

## Phase 4 — L3/L4: History + render (lenses 1, 4, 5)
Append-only history store. Web surface: structure, health, timeline. Ship these
three first — they deliver the "everything under control" glance.

**Acceptance:** a node's version change is visible on the timeline within one
commit; health colour matches `ent eval` output. ✓ **Met** — `ent snapshot`
records composite versions (deduped, so only *changes* land) + eval verdicts to
an append-only log; `ent render` builds a self-contained HTML surface whose Health
lens computes verdicts via the same `run_tier0`, so the colour matches `ent eval`
by construction. `tests/test_history.py` + `tests/test_render.py`.

Implemented:
- `src/ent/version.py` — composite version (code/prompt/config/model), deterministic
- `src/ent/history.py` — append-only JSONL event log; version dedup; timeline reads
- `src/ent/gitinfo.py` — commit + timestamp stamping (degrades outside git)
- `src/ent/commands/snapshot.py` — `ent snapshot`: record versions + verdicts
- `src/ent/render.py` + `src/ent/commands/render.py` — `ent render`: lenses 1
  (structure), 4 (health), 5 (timeline) as one self-contained page; `--serve` too

## Phase 5 — L4 remainder: lenses 2, 3, 6
Flow, trace, blast radius. ☑ **Done.**

- **Flow (2):** directed edges + per-node volume (traffic count from recorded traces).
- **Trace (3):** `history.capture_trace(root, trace_id=...)` records a request's
  hops (node, latency, status, cost) from `@ent.node()` spans; the lens shows
  latency per hop. `src/ent/history.py`.
- **Blast radius (6):** `render.blast_radius(view, node_id)` computes transitive
  downstream dependents ranked by direct contract coupling; the page highlights
  them interactively. `src/ent/render.py`.

`tests/test_lenses.py` covers trace recording (incl. error hops), flow volume,
and blast-radius reachability/ranking.

## Phase 6 — L5: Scoped edit loop
Context assembler, claim-boundary enforcement, auto tier0 rerun, approval gates.

**Acceptance:** clicking a node and requesting a change produces an edit confined
to `claims`, with a pass/fail verdict, without loading unrelated files.

---

## MVP — the two-week slice (SPEC.md §9)

Resist building all six lenses. Prove the loop end to end on **five nodes** of
one real project (the `examples/greenfield/` project is that shape):

1. Manifest schema + validator
2. Extractor emitting `graph.json` (static only, no runtime yet)
3. tier0 eval runner
4. **One** rendered lens: health-coloured structure map
5. Click a node → see its manifest, version, last eval, claimed files
