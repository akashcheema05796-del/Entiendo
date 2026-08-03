# Entiendo — status

The single source of truth for *what is implemented today*. When you change what
the project can do, update this file in the same PR — narrative docs (README,
SPEC, LEXICON, `docs/`) should agree with it. If they drift, this file wins until
they're reconciled.

- **Version:** `0.1.0` (pre-release)
- **Runtime:** Python (`ent` CLI). Runtime deps minimal (pyyaml, jsonschema);
  heavier features behind extras (`.[dev]`, `.[serve]`, `.[mcp]`).
- **Tests:** `python -m pytest -q` → **352 passing** (~8s).

**PLAN_v6 (trust hardening) — in progress:** Phase 0 verification ✅
(`docs/V6_VERIFICATION.md` — all 13 audit questions answered with file:line
evidence; task 3.3 overlapping-claims CLOSED as already enforced at
`extractor.py:100-112,346-354`). Confirmed-required: eval sandbox (1.1),
bootstrap-CI verdicts (1.2), proposal base-hash guard (1.3), single claims
authority (1.4), claims hook (2.1), tier1 health lens (2.2), append durability
(3.1), ent ci tier1 (3.2), queue atomicity/CSRF (3.4), live reload (4.2), polish
(5.x). Phase 1 ✅ — sandboxed eval runner (timeout + rlimits, TIER0_TIMEOUT), paired-bootstrap tier1 verdicts (CI bounds + n + MDE; threshold-legacy fallback), base-hash guard on proposal approve (stale → zero writes), and the single claims authority `claims.py` (realpath + containment) routed through all write paths. Phase 2 ✅ — the enforce_claims PreToolUse hook (out-of-claims edits mechanically denied in hooked sessions), tier1 significance on the health lens (statVerdict + CI + n; ring colours; 'red only on statistically meaningful movement'), the live Bridge integration test (generated content, no pre-stored diff), and a one-command demo reset. Live H5 recording still Mehar's (open residual). Phases 3-5 next.

**PLAN_v5 (close the loop) — in progress:** V0 audit ✅ (`PLAN_v5_AUDIT.md`);
V1 edge verification ✅ — edges flip declared→verified from recorded runtime spans
(`ent extract --with-spans`), with a `verificationSource`/`observationCount`
tri-state and a staleness rule (a code change reverts verification until
re-observed). V2 golden-set spread ✅ — refundly.parse_email gets a real (non-saturated) tier1 golden set (baseline 0.78, not 1.0) that discriminates: an injected regression goes REGRESSED, cosmetic noise stays within band. V3 blessedBy + kill-the-CI-bless-bypass ✅ — blessing needs a real identity (--as → config → git email, never "unknown") and an interactive TTY (CI can't bless);
V4 H5 pre-flight ✅ — the steer→edit→propose→approve seam is verified live-ready with an end-to-end regression test + docs/H5_DEMO_RUNBOOK.md. **PLAN_v5 code is complete (V0–V4)**; the uncut live H5 screen-recording (V4.3) is the human's to capture.

## Implemented

The full control-plane loop works end to end — declare units → reconcile the
graph → instrument → execute + eval → record history → render the Universe →
steer + approve through the unit.

| Track | Scope | State |
|---|---|---|
| **L0 — Boundaries** | manifest schema + validator; `ent init` / `ent new` (fixture-first) | ✅ |
| **L1 — Extractor** | AST import analysis; declared-vs-actual edge reconciliation; drift fails the build | ✅ |
| **L2 — Instrumentation + evals** | `@ent.node()` spans + `ent.guard`; tier0 *executes* the unit; tier1 golden; tier2 judge scaffold | ✅ |
| **L3 — History** | append-only versions / evals / traces; composite fingerprints | ✅ |
| **L4 — The Universe** | one navigable canvas, six real lenses (structure/flow/trace/health/timeline/blast) | ✅ |
| **L5 — Steer + approve** | scoped edit loop; `ent serve`; the Bridge (operator loop); diff-first approval | ✅ |
| **Phase 7 — Real evals** | restricted-AST invariants, isolation, GREEN/RED/UNTESTED/ERROR | ✅ |
| **v3 (PLAN_v3 A–G)** | units/fingerprints vocabulary, Universe, Bridge, agentic units + trajectory, replay, retrofit | ✅ |
| **v4 (PLAN_v4 H0–H5)** | rendered agentic interiors, trace playback, timeline scrubber, cost overlay, diff-first approval | ✅ |

**CLI (all wired):** `init` · `new` · `validate` · `extract` · `eval` · `bless` ·
`baseline` · `snapshot` · `render` · `pin` · `replay` · `edit` · `serve` · `mcp` ·
`retrofit` · `doctor` · `fixtures` · `ci`.

**Examples:** `greenfield` (5 units — the MVP walkthrough) · `refundly` (6-unit
agentic pipeline — the v4 demo: interiors, trajectory, approval) · `legacy`
(unmanaged input for `ent retrofit`).

## Not yet — the roadmap

Ordered by impact (see the gap analysis for detail).

1. **Language path** — *spike landed.* The extractor now runs through a
   language-agnostic seam (`ent.languages`) with a Python extractor and a
   minimal **TypeScript/JS** proof-of-concept; `ent extract` reconciles a TS
   project — including tsconfig `paths`/`baseUrl` aliases (see `docs/multi-language.md`),
   Python path unchanged. Still Python-only past extraction: instrumentation
   (`@ent.node()`), the invariant evaluator, and `contract.entrypoint` execution.
   Next: a real tokenizer, and a language-agnostic execution/eval seam.
2. **Live telemetry → Universe** — Trace / cost / health are strong on fixtures
   and recorded traces; continuous production capture (OTel auto-ingest, durable
   Parquet/DuckDB by default) is thin.
3. **Soft adoption + fixture assist** — `ent extract --soft` (warn-only reconcile:
   drift → warning, structural still fails) ✅ and `ent fixtures <unit>` (scaffold
   smoke-fixture skeletons from recorded traces — dep stubs pre-wired, error
   traces flagged; `input` is a placeholder since traces don't record payloads) ✅
   both landed, plus `--min-coverage <pct>` on `ent extract`/`ent ci` (a
   coverage-ramp target a migrating team raises over time). ✅ §3 complete.
4. **Team surface** — `ent serve` is single-operator (localhost stdlib, file-queue
   steering); no auth / RBAC / shared proposals. (`ent doctor` ✅ and `ent ci` —
   one validate+reconcile+eval gate for CI/pre-commit, see `docs/ci.md` — ✅ landed.)
5. **Eval depth** — tier2 needs a default judge harness; behaviour delta needs
   goldens; no sandboxed side-effect simulation.
6. **Packaging & first-run** — version `0.1.0`, no binary distribution.

## Explicitly deferred (PLAN_v4 §9)

WebGL renderer · SSE/push steering · presence/multiplayer · `apiVersion` bump +
full mechanical `node`→`unit` rename · advanced retrofit UX.

---

*Keep this current: it exists so the narrative docs have one place to agree with.*
