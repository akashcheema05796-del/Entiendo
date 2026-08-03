# PLAN_v5 — Close the Loop

> Scope: everything left between "structurally complete" (post-v4, PRs #25–#30,
> 251 tests) and "every link in the loop is real." Four phases, strict order.
> Do not start a phase before the previous phase's acceptance criteria pass.
>
> Convention: this plan follows the Audit → Plan → Verify loop. Phase V0 is
> mandatory and produces the file map that later phases reference.

---

## V0 — Audit & locate (do this first, no code changes)

Before implementing, produce `PLAN_v5_AUDIT.md` answering:

1. Where does the extractor's edge reconciliation live, and what data structure
   represents an edge? (Expected: fields for declared/actual; confirm whether a
   `verified` field exists and is simply never set, or doesn't exist.)
2. Where are recorded runtime spans stored for `examples/refundly`
   (the recorded traces), and in what format? Where does `ent replay` read them?
3. Where does `build_view()` surface edge state to the render layer, and what
   does the Universe currently render for an edge's verification state?
4. Where is tier1 golden scoring computed (the code path that produced the
   trivial 1.0000), and where is the significance comparison against baseline?
5. Where is `blessedBy` populated, and where is `ent bless --yes` parsed?
6. Exact test counts and locations for extractor, eval runner, bless flow.

Every task below says "[locate: V0.n]" where the audit answer determines the
file. Do NOT guess paths — if the audit answer is ambiguous, stop and report.

**Acceptance V0:** `PLAN_v5_AUDIT.md` exists with concrete paths + line-level
references for all six questions, and names any finding that invalidates a
phase below (report before proceeding).

---

## V1 — Edge verification: spans → extractor feedback  (residual #1)

**Goal:** edges flip from `declared` to `verified` when runtime spans confirm
them. This makes the core product claim ("verified, not inferred") true.

### Tasks
1. **Edge state model** [locate: V0.1]. Edge gains an explicit tri-state:
   `declared` (in manifest, never observed), `verified` (declared AND observed
   in spans), `undeclared_observed` (observed but not in manifest — this should
   already be the reconciler's build-failure case; confirm and keep).
   Add `lastVerifiedAt` timestamp and `observationCount`.
2. **Span ingestion pass** [locate: V0.2]. New reconciler stage: read the span
   store / recorded traces, match parent-child span pairs by
   `entiendo.node_id` attributes, emit observed edges. Wire into
   `ent extract` behind a flag first (`ent extract --with-spans <path>`),
   then make it default when a span source is configured.
3. **Verification semantics.** An observed edge verifies a declared edge iff
   (caller node_id, callee node_id) match a `dependencies.calls|reads|writes`
   declaration. reads/writes verification: match span attributes for the
   state node touched, if present in spans; if span data cannot distinguish
   reads from writes, verify at edge level and record
   `verificationGranularity: edge` — do not fake precision.
4. **Graph output** [locate: V0.1]. `graph.json` edges carry the tri-state +
   metadata. Bump nothing in `apiVersion`; this is additive.
5. **Render** [locate: V0.3]. Universe renders the three states distinctly:
   verified = solid, declared-only = visibly tentative (reduced
   opacity/dashed), undeclared_observed never renders (it's a build failure).
   The dossier's edge list shows state, observationCount, lastVerifiedAt.
6. **Staleness rule.** A previously-verified edge whose node composite version
   changed reverts to `declared` until re-observed. Verification is per
   (edge, caller composite version) — otherwise verification rots silently.

### Tests
- Unit: span-pair matching, tri-state transitions, staleness on version change.
- Integration: full refundly replay → assert >0 verified edges and exact
  expected set; add one fabricated declared edge to a fixture manifest →
  assert it renders declared-only and is listed in a new
  `coverage.json`-adjacent report section `unverifiedDeclaredEdges`.

### Acceptance V1
`ent extract --with-spans` on examples/refundly produces graph.json where the
six-stage pipeline's call edges are `verified`; the Universe visually
distinguishes them; a fabricated never-fired edge stays tentative; changing a
node's code reverts its outgoing verified edges to declared; all existing 251
tests still pass.

---

## V2 — Golden dataset spread + significance proof  (benchmark half A)

**Goal:** tier1 can actually discriminate. A benchmark everything passes at
1.0000 is not a benchmark.

### Tasks
1. **Diagnose the 1.0000** [locate: V0.4]. Determine whether the trivial score
   is (a) dataset too easy, (b) metric saturated, or (c) scoring bug (e.g.
   comparing output to itself). Fix (c) first if present — report it.
2. **Rebuild refundly golden set.** Author `evals/<node-id>/golden_v3.jsonl`
   rows spanning difficulty: clear-cut cases, boundary cases (amounts at
   policy thresholds, ambiguous fraud signals), and known-hard cases the
   current implementation gets partially wrong. Target baseline in the
   0.75–0.92 band, not 1.0. Mark all rows `humanBlessed: false` — Mehar
   blesses via `ent bless` after review (do NOT self-bless; see V3).
3. **Significance harness.** Add `ent eval <node> --inject-regression <patch>`
   test utility OR a test-only fixture pair: variant R (deliberate behavioral
   regression, e.g. fraud threshold moved) and variant N (noise-level change,
   e.g. cosmetic refactor). 
4. **Verdict wiring** [locate: V0.4]. Confirm minRuns and significance from the
   manifest are actually honored in the verdict (not just parsed): variant R
   over minRuns → red; variant N over minRuns → "within band." If the verdict
   currently collapses tiers or signals, fix per the no-verdict-collapse rule.

### Tests
- Scoring unit tests with hand-computed expected metric values (catches
  bug-class (c) permanently).
- Statistical: R detected, N not, across minRuns; deterministic seeds.

### Acceptance V2
Refundly tier1 baseline lands strictly inside (0, 1); injected regression
turns the node red in the Health lens; injected noise stays within band;
verdict output shows per-signal detail (no collapse).

---

## V3 — Accountability: blessedBy + kill the CI bypass  (benchmark half B)

**Goal:** "AI drafts, human blesses" is enforced, not aspirational.

### Tasks
1. **Identity resolution** [locate: V0.5]. `blessedBy` resolves from, in
   order: explicit `--as <identity>` flag (interactive only), configured
   `ent` user (config file), `git config user.email`. If none resolve →
   blessing FAILS with a clear error. `"unknown"` is no longer a writable
   value; validator rejects it in history entries going forward (do not
   rewrite existing history — append-only stays append-only; add a one-time
   migration note instead).
2. **`ent bless --yes` decision — implement option A:** `--yes` skips the
   confirmation prompt but STILL requires an interactive TTY
   (`isatty(stdin)`). In non-TTY environments (CI), `ent bless` exits
   non-zero with: "Blessing requires an interactive session. Baselines are a
   human gate." Add `ENT_ALLOW_NONINTERACTIVE_BLESS` escape hatch REFUSED —
   do not add any env-var bypass; that recreates the hole.
3. **History surfacing** [locate: V0.5]. Dossier + timeline show blessedBy on
   every baseline event. `ent eval` output includes current baseline's
   blesser and bless date.

### Tests
- Non-TTY bless attempt fails (subprocess test with stdin not a tty).
- Identity fallback chain unit-tested; no-identity case fails.
- Validator rejects `blessedBy: unknown` on new history writes.

### Acceptance V3
Blessing from a CI-like environment is impossible; every new baseline carries
a real identity; the identity is visible in the Universe dossier and CLI.

---

## V4 — Live H5 exercise: steer → diff → approve  (residual #2)

**Goal:** the loop runs end-to-end in a REAL Claude Code session, recorded.
This phase is mostly Mehar-driven; Claude Code's job is pre-flight fixes.

### Tasks
1. **Pre-flight audit.** Walk the H5 path in code and list every seam:
   steering queue → context assembly (manifest + claims + neighbor contracts
   only) → edit → tier0 auto-rerun → diff render → proposal → approval →
   merge. For each seam, name the failure mode if exercised live and fix
   anything that only ever ran under test harness assumptions (mocked
   clocks, fixture-only paths, hardcoded IDs).
2. **Demo script.** Write `docs/H5_DEMO_RUNBOOK.md`: exact node to steer
   (pick a refundly node with `approval.required: true`), exact steering
   instruction, expected diff shape, expected tier0 verdict, approval click,
   post-merge state. Include reset instructions so the demo is repeatable.
3. **Live run (Mehar).** Execute the runbook in a real session, screen-
   recorded, uncut. Any failure → fix → re-run from reset. The recording is
   the launch/YC artifact.

### Acceptance V4
One uncut recording: node clicked → steer → Claude Code edit confined to
claims → tier0 verdict in Universe → diff → approve → merge. Zero manual
intervention outside the product surface.

---

## Out of scope for v5 (do not pull forward)
- Placement/residency + per-unit model governance (contract dimensions —
  captured in spec horizon, build post-launch)
- Retrofit / proposed-manifest ingestion
- Team mode, multi-language extraction

## Definition of done for v5
All four phases' acceptance criteria pass; full test suite green (target:
251 + new, zero regressions); `PLAN_v5_AUDIT.md` updated with a closing
verification section re-checking each phase's claims against the actual
tree (per the skeptical-verification norm: assume the first "done" is wrong
until re-audited).
