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
| 6 | L5 — Scoped edit loop | ☑ `ent edit` — context + boundary + verdict + approval |

**All phases complete.** The full loop L0 → L5 is implemented.

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
to `claims`, with a pass/fail verdict, without loading unrelated files. ✓ **Met** —
`ent edit <node>` assembles a context of only the node's claimed file bodies +
immediate neighbours' contracts (no bodies) + recent evals + baseline;
`ent edit <node> --changed <paths>` enforces the claim boundary, reruns tier0 for
a pass/fail verdict, shows the blast radius, and applies the approval gate.
`tests/test_editloop.py`.

Implemented:
- `src/ent/editloop.py` — `assemble_context()` (the manifest IS the retrieval
  index — nothing outside the node is loaded), `check_boundary()`, `review_edit()`
  (boundary + tier0 + blast radius + approval → status).
- `src/ent/commands/edit.py` — `ent edit`: show scoped context, or review an edit
  (exit 0 ready/awaiting-signoff, 1 blocked, `--json` for machine use).

---

## Phase 7 — Real Evals ☑

The phase that makes `GREEN` mean "the node behaved," not "the YAML is valid".
A node's eval now **executes the node**. See `docs/phase7.md` for detail.

- **7.1 Execution contract** — `contract.entrypoint: <path>::<callable>` (must be
  claimed); resolver + decorator cross-check (drift). `src/ent/evals/entrypoint.py`.
- **7.2 Isolation** — tier0 runs with no I/O: dependency calls are served from
  fixture stubs; an unstubbed call is `TIER0_IO_VIOLATION`. `src/ent/testing.py`.
- **7.3 Real invariants + verdicts** — a restricted AST evaluator (no eval/exec)
  evaluates invariants against real output; verdicts GREEN/RED/UNTESTED/ERROR;
  the render surface shows "executable N/M". `src/ent/invariants.py`, `verdicts.py`.
- **7.4 tier1 runner** — golden datasets, metrics, minRuns, anti-flicker
  statistics (§7: WITHIN_BAND/REGRESSED/IMPROVED/UNSTABLE), budgets (DEGRADED).
- **7.5 Blessing + baselines** — `ent bless` signs dataset content (void on
  change → advisory); `ent baseline accept` promotes a pending baseline.

**One-line test (§15):** break `ranker.py`, run `ent eval retrieval.chunk_ranker`
→ RED naming the failed invariant with the real numbers
(`len(output.chunks)=2 <= input.k=1`). Covered by `tests/test_evals.py`.

## Extensions (beyond the spec)

Built after the L0 → L5 phases, one PR each, CI-gated.

| # | Extension | Status |
|---|---|---|
| E1 | CI (GitHub Actions: pytest + validate/extract/eval) | ☑ |
| E2 | tier1/tier2 eval runners (superseded/extended by Phase 7) | ☑ |
| E4 | Retrofit path (§12 v2) — AI-proposed manifests | ☑ `ent retrofit` |

**E4 — retrofit.** `ent retrofit <root>` infers node boundaries in an unmanaged
repo (group by directory, kind from extensions, deps from static import
analysis, entrypoint from a single public function) and stages one manifest
*proposal* per node under `entiendo/proposals/`, each with a confidence + notes.
`--accept <id>` / `--accept-all` promotes them into place — a semi-automated
migration reviewed node by node, never a silent scan. `examples/legacy/` is the
unmanaged input; `src/ent/retrofit.py`; `tests/test_retrofit.py`.

**E2 — tier1/tier2.** `src/ent/evals/metrics.py` (ndcg@k / exact_match /
accuracy), `entrypoint.py` (import a node's `@ent.node()` callable), and
`runner.run_tier1`/`run_tier2`. tier1 replays `minRuns` times, scores vs baseline
with a significance threshold (red only on meaningful regression, §5.3); tier2 is
the rubric-driven LLM-judge scaffold (judge wired explicitly, never faked). The
greenfield ranker is runnable, so `ent eval retrieval.chunk_ranker --tier 1`
scores a real ndcg@5. `tests/test_tier1_tier2.py`.

## MVP — the two-week slice (SPEC.md §9)

Resist building all six lenses. Prove the loop end to end on **five nodes** of
one real project (the `examples/greenfield/` project is that shape):

1. Manifest schema + validator
2. Extractor emitting `graph.json` (static only, no runtime yet)
3. tier0 eval runner
4. **One** rendered lens: health-coloured structure map
5. Click a node → see its manifest, version, last eval, claimed files
