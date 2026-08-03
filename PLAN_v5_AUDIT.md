# PLAN_v5 — V0 Audit & Locate

Read-only audit (no code changes). Concrete paths + line references for the six
V0 questions, and any finding that reshapes a later phase. Current tree: **299
tests**, `main` @ the post-loop state.

---

## V0.1 — Edge reconciliation + the edge data structure

- **Lives in:** `src/ent/extractor.py`, `_build_edges()` (from `def _build_edges` at
  `extractor.py:179`); emitted edge shape built at `extractor.py:191` and
  serialized at `extractor.py:262-268`.
- **Edge structure:** an in-progress dict per `(from, to)` pair —
  `{"kinds": set(), "declared": bool, "verified": bool, "evidence": [str]}`
  (`extractor.py:191`). Serialized edge (in `graph.json`) has:
  `from, to, kinds[], declared, verified, evidence[]`.
- **How the fields are set:**
  - `declared` ← a manifest `dependencies.calls|reads|writes|config` entry
    (`extractor.py:206-207`).
  - `verified` ← **static import analysis** confirming the edge
    (`extractor.py:225`, via the language extractor seam `languages.for_file`).
  - `undeclared` (observed-not-declared) is the drift **build failure**
    (`extractor.py:251-258`, `DRIFT_PREFIX`).

> **FINDING (reshapes V1):** the `verified` field **exists and is already set** —
> but its meaning today is *"confirmed by static import analysis,"* not *"confirmed
> by a runtime span."* V0.1 anticipated "confirm whether `verified` exists and is
> simply never set" — it is set. So V1 must **distinguish evidence sources**, not
> add a field to something empty. Recommended: keep `verified` as the roll-up but
> add `verificationSource` (`import` | `span`) and the tri-state metadata
> (`lastVerifiedAt`, `observationCount`), so an import-verified edge and a
> span-verified edge are not conflated. The plan's tri-state
> (`declared` / `verified` / `undeclared_observed`) maps cleanly onto the existing
> three code paths above.

---

## V0.2 — Recorded spans / traces, and what `ent replay` reads

- **Stored in:** `examples/refundly/entiendo/history/events.jsonl` (a tracked
  fixture). Event kinds present: `version` ×7, `eval` ×7, **`trace` ×3**.
- **Trace format:** a `trace` event has keys
  `commit, hops, kind, seq, totalMs, traceId, ts`. Each **hop** is a flat record:
  `{node, duration_ms, status, cost_usd, tokens}` (produced by
  `history.capture_trace` at `history.py:163-193` from `@ent.node()` spans).
- **`ent replay` reads:** `src/ent/replay.py` — `history.read_events(root)`
  (`replay.py:34`); `replay(root, node_id, against)` at `replay.py:81`. Replay
  compares fingerprints, not spans.

> **FINDING (reshapes V1.2 / V1.3):** recorded hops are a **flat, ordered list
> with no parent→child span links** (no `parentNode`, no span id). So V1's
> "match parent-child span pairs by `entiendo.node_id`" **cannot read caller→callee
> directly from the current data** — the linkage isn't captured. Two honest
> options, pick in V1:
> 1. **Enrich capture** — add a `parent` node id to each hop in
>    `history.capture_trace` (spans already nest via contextvars in
>    `tracing.py`), regenerate the refundly fixture, then match true pairs.
> 2. **Co-occurrence verification** — an observed edge `A→B` is verified when a
>    trace contains a hop for `A` and a hop for `B` **and** `A→B` is declared;
>    record `verificationGranularity: trace` (weaker than `edge`) so precision
>    isn't faked (satisfies the plan's "do not fake precision" rule).
> Option 1 is the stronger claim and is preferred if the fixture regen is
> contained; V1 should attempt it and fall back to 2 with the granularity flag.

---

## V0.3 — Where `build_view()` surfaces edge state, and what the Universe renders

- **build_view:** `src/ent/render.py:80` — `"edges": result.graph["edges"]`
  (passed through verbatim from the extractor).
- **Universe render:** `src/ent/universe.html` — edges are de-duped into a map
  carrying `verified` (`universe.html:288-292`); rendered as animated particles
  whose **count, speed, and opacity depend on `verified`**
  (`universe.html:352-359`, `:373-374`): verified → 3 particles, faster, brighter
  (`rgba(...,.9)`, edge alpha `0.5`); declared-only → 2 particles, slower, dimmer
  (`rgba(...,.5)`, edge alpha `0.26`). The dossier edge line shows a `✓` for
  verified (`openDossier` edgeLine).

> **FINDING (V1.5 is additive):** there are already **two** visual states
> (verified vs not). V1 wants **three**: verified (solid), declared-only (visibly
> tentative — the current dim state is close; make it dashed for clarity), and
> `undeclared_observed` which **never renders** (it's a build failure — already
> true). The dossier must add `observationCount` + `lastVerifiedAt`.

---

## V0.4 — tier1 golden scoring (the trivial 1.0000) + significance

- **Scoring:** `src/ent/evals/runner.py`, `run_tier1()` at `runner.py:240`. Each
  run scores rows with `metric(out, row["expect"])` (`runner.py:295`) — **output
  vs. the row's declared `expect`**, i.e. *not* output-compared-to-itself.
- **Significance/minRuns:** read from baseline record or golden
  (`runner.py:278-281`) and **honored** in the verdict via
  `_stat_verdict(mean, baseline, spread, significance)` (`runner.py:313`);
  `delta = mean - baseline` (`runner.py:314`); IMPROVED/baseline-none proposes a
  pending baseline, never auto-promotes (`runner.py:316-320`).
- **The 1.0000:** it is **greenfield** `retrieval.chunk_ranker`
  (`examples/greenfield/evals/retrieval.chunk_ranker/golden_v2.jsonl`, metric
  `ndcg@5`, baseline `0.81` — manifest lines 52-54). ndcg@5 saturates to 1.0 on
  the easy rows.

> **FINDING (classifies the bug-class):** this is **(a) dataset too easy / (b)
> metric saturated**, **not (c) a scoring bug** — `metric(out, row["expect"])`
> compares to the expected value, so there is no output-vs-self defect to fix.
> **FINDING (reshapes V2):** `examples/refundly` has **no tier1/golden set at all**
> — `refundly.decide` only ships `smoke.jsonl` + `trajectory.jsonl`
> (`examples/refundly/evals/refundly.decide/`). So V2 "rebuild refundly golden
> set" means **author one from scratch** (`golden_v3.jsonl`) for a refundly node.
> **V2 RISK:** tier1 executes the node, so the chosen node must be *runnable in
> isolation* with a `contract.entrypoint` and a scorable output; V2 must confirm
> `refundly.decide` (or a simpler node) is runnable before authoring rows, or add
> the entrypoint. Verify first, report if not runnable.

---

## V0.5 — `blessedBy` population + `ent bless --yes`

- **`blessedBy`:** set in `src/ent/commands/bless.py:67` —
  `blessed_by = args.by or os.environ.get("USER", "unknown")` — then written by
  `baselines.write_blessing(...)` (`baselines.py:84-91`, stores `blessedBy` /
  `blessedAt`).
- **`--yes`:** declared at `bless.py:30` (`"skip the confirmation prompt"`); the
  prompt/abort path is `bless.py:64`. **There is no `isatty` check anywhere** —
  `--yes` currently lets a non-interactive/CI environment bless.

> **FINDING (confirms V3 targets, both real):**
> - **V3.1** — identity today is `--by` → `$USER` → the literal string
>   `"unknown"`. The chain must become `--as` → `ent` config → `git config
>   user.email`, and **fail** if none resolve; `"unknown"` must stop being a
>   writable value (validator rejects it on *new* history writes only —
>   append-only history is not rewritten; add a migration note).
> - **V3.2** — the CI-bypass hole is real: `--yes` has no TTY guard. V3 adds
>   `isatty(stdin)` and refuses any env-var escape hatch.

---

## V0.6 — Test counts + locations (baseline for "zero regressions")

| Area | File | tests |
|---|---|---|
| Extractor / reconciler | `tests/test_extractor.py` | 9 |
| TS extractor (seam + spike) | `tests/test_ts_extractor.py` | 7 |
| TS tsconfig aliases | `tests/test_ts_tsconfig.py` | 7 |
| tier0 eval runner | `tests/test_evals.py` | 4 |
| tier1 / tier2 runner | `tests/test_tier1_tier2.py` | 14 |
| bless / baseline flow | `tests/test_bless_baseline.py` | 4 |
| **Full suite** | — | **299 collected** |

(The plan's "251 + new" target predates the v5 gap-fix loop; the real regression
floor is **299**. Keep all 299 green; add per phase.)

---

## Summary of findings that reshape phases

1. **V1:** `verified` already exists and means *import-confirmed*; add a
   `verificationSource` + tri-state metadata rather than treating it as empty.
2. **V1:** recorded hops are **flat, no parent links** — either enrich
   `capture_trace` with a `parent` node id (preferred) or verify by trace
   co-occurrence with `verificationGranularity` (do not fake edge-level precision).
3. **V2:** the 1.0000 is dataset/metric saturation, **not** a scoring bug (c);
   and **refundly has no golden set** — V2 authors one, and must first confirm the
   chosen node is runnable in isolation (entrypoint + scorable output).
4. **V3:** both targets confirmed real — identity falls back to `"unknown"`, and
   `--yes` has no TTY guard.
5. **Regression floor is 299 tests**, not 251.

None of these findings *invalidate* a phase — V1–V3 proceed with the adjustments
noted above. V4 (live H5 recording) remains human-driven; Claude Code does the
pre-flight audit + runbook.
