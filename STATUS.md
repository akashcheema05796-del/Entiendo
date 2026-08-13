# Entiendo — status

The single source of truth for *what is implemented today*. When you change what
the project can do, update this file in the same PR — narrative docs (README,
SPEC, LEXICON, `docs/`) should agree with it. If they drift, this file wins until
they're reconciled.

- **Version:** `0.2.0` (first public beta — see `CHANGELOG.md`; Apache-2.0;
  wheel ships the manifest schema so a clean `pip install` works outside a
  checkout; CI runs pip-audit + publishes a CycloneDX SBOM; `release.yml`
  publishes to PyPI via Trusted Publishing once the publisher is configured
  on pypi.org)
- **Runtime:** Python (`ent` CLI). Runtime deps minimal (pyyaml, jsonschema);
  heavier features behind extras (`.[dev]`, `.[serve]`, `.[mcp]`).
- **Tests:** `python -m pytest -q` → **579 passing** (~30s), plus an optional
  browser suite: `pytest tests/frontend/frontend_universe.py` (16 Playwright
  tests, not collected by default).

**Self-hosting ✅** — the repo manages itself: **14 semantic units** under
`units/` (engine: contracts/versioning/graph · quality: evalkit/trust ·
runtime: history/observer/timetravel · surface: universe/cli · agents:
bridge/retrofit/plugin · dist: packaging), every file claimed or explicitly
acknowledged in `entiendo/unclaimed.txt` (unaccounted = 0), all declared edges
verified by the reconciler, and CI gates `ent validate` + `ent extract --check`
at the repo root. **All 14 units execute real tier0 evals and are GREEN** — the harness
seam (`contract.harness`) closed the last hole: units whose entrypoint takes
`(node, root)`, `(root, node_id)` or no arguments at all are now runnable, and
8 of the 9 it unblocked are proven to go RED under a deliberate mutation of
the code they test. The ninth (`ent.evalkit`) is self-referential — a mutation
that disables invariant enforcement cannot be caught by an invariant — and is
covered by the pytest suite instead (verified: that mutation fails 3 tests). Dogfooding fallout fixed in the same pass: all file
walks stop at nested project roots (shared `iter_project_files`), the sandbox
protects its stdout JSON protocol from print()ing entrypoints, and the
enforce_claims hook now allows explicitly-unclaimed (acknowledged) files —
during this retrofit the hook mechanically denied an edit to its own file
until `ent.plugin` claimed it with human sign-off, which is the system working.

**PLAN_v6 (trust hardening) — in progress:** Phase 0 verification ✅
(`docs/V6_VERIFICATION.md` — all 13 audit questions answered with file:line
evidence; task 3.3 overlapping-claims CLOSED as already enforced at
`extractor.py:100-112,346-354`). Confirmed-required: eval sandbox (1.1),
bootstrap-CI verdicts (1.2), proposal base-hash guard (1.3), single claims
authority (1.4), claims hook (2.1), tier1 health lens (2.2), append durability
(3.1), ent ci tier1 (3.2), queue atomicity/CSRF (3.4), live reload (4.2), polish
(5.x). Phase 1 ✅ — sandboxed eval runner (timeout + rlimits, TIER0_TIMEOUT), paired-bootstrap tier1 verdicts (CI bounds + n + MDE; threshold-legacy fallback), base-hash guard on proposal approve (stale → zero writes), and the single claims authority `claims.py` (realpath + containment) routed through all write paths. Phase 2 ✅ — the enforce_claims PreToolUse hook (out-of-claims edits mechanically denied in hooked sessions), tier1 significance on the health lens (statVerdict + CI + n; ring colours; 'red only on statistically meaningful movement'), the live Bridge integration test (generated content, no pre-stored diff), and a one-command demo reset. Live H5 recording still Mehar's (open residual). Phase 3 ✅ — durable locked history append (flock + fsync, `seq` under the lock, `v: 1` schema field; concurrent writers proven), `ent ci` tier1 stage on BLESSED goldens with Phase-7 severity exit codes (0 pass · 1 REGRESSED · 2 ERROR · 4 UNSTABLE/DEGRADED, max across stages; unblessed = advisory, never blocks), atomic steering claims (`O_CREAT|O_EXCL` — exactly one concurrent consumer wins), idempotent `post_verdict`/`propose_from_outcome` (`{duplicate: true}`, no second side-effect), Handler-level CSRF on the serve surface (X-Ent-Csrf token minted at render; loopback bind verified), and extractor blind-spot honesty (`possibleUndeclaredDynamicDep` warnings in graph/CLI/dossier; TS-PoC edges tagged `ts-poc` and rendered declared-grade). Phase 4 ✅ — the Universe proven in a real browser (11-test Playwright suite driving `ent serve`: six lenses, trace playback, timeline scrub, CSRF-protected steer/approve round-trips, live-reload drift banner, empty-repo invitation; optional CI job gated on browser presence), live reload (`ent dev` / `serve --watch`: mtime watcher + `/api/version` long-poll + auto page reload; a broken tree serves the last good view with a drift banner; threading server so long-polls never starve requests), Claude Code plugin packaging (`.claude-plugin/plugin.json` + `marketplace.json` bundling the MCP server, operator skill, and claims hook; MCP elicitation settles approval-gated proposals in-line with graceful web fallback), and a discriminating tier1 golden for `refundly.decide` (baseline 0.80 — two rows encode ideal behaviour the agent gets wrong; stays unblessed for Mehar). Phase 5 ✅ — hashing honesty (secret config values never enter the composite — rotation is not a behaviour change, Invariant 6; CRLF→LF normalisation for prompt/config so a Windows checkout mints no phantom version, recomputes recorded as ordinary version events), budget label honesty (a tiny window's "p95" is labeled `max of N`), the bless CI-bypass guard rewritten behaviourally (every plausible env-var escape hatch set → still refused, nothing written), the three silent excepts narrowed or made loud (trace-capture composite failures warn on stderr), canvas scale honesty (particle cap >100 units + offscreen skip; legacy `blessedBy: unknown` renders as "unverified historical blessing"), and 5.9 stale-graph warning MOOTED by 4.2 (serve/render always re-extract; `ent dev` live-reloads; the committed artifact is covered by `ent extract --check` in CI). **All PLAN_v6 items listed for Phase 5 landed — nothing deferred.**

**PLAN_v7 (workspace surface) ✅ complete** — the Universe is now a windowed
workspace: click a star and the Logical Unit opens as a draggable glass window
over the living map (five tabs: manifest · contract · evals · history · blast,
rendered entirely from the embedded `payloadVersion: 2` — zero fetches, works
from disk); canvas tethers tie each window to its node; the focused window
drives the canvas selection and its blast tab flips the lens; a window covering
its own node auto-pans the viewport (graph coordinates never mutated); layouts
persist to `entiendo/workspace.json` through `ent dev` (CSRF-guarded, debounced,
stale ids dropped, git-ignored by default); lens keys 1–7, Esc clears the sky,
dock restores; gate integrity proven (no new MCP tools, no bless affordance,
zero diff to claims/sandbox/steering). Statistics deviation, declared: no
p-values exist — `significant` means the bootstrap CI excludes zero.

**Research round 2 (propose-verify architecture) ✅ complete** — six steps,
one PR each: the **oracle boundary** made mechanical (the claims hook
fail-closes on history/baselines/steering, the generated map, and blessed
goldens; bypassing writes still void the blessing signature; adversarially
tested), **oracle-class provenance** on golden rows (implementation-derived
rows quarantined at bless time behind an explicit human flag; harvested rows
tagged by construction), **adapter capability manifests** (each language
adapter's blind spots published in `graph.json`, every edge graded
`resolution: complete|partial|none`, `ent doctor` prints what the map cannot
see), the **effect probe** (sandbox audit hook; a false `sideEffects: none`
goes RED — first catch was `ent.surface`'s own git subprocess; absence of
effects stays graded evidence per Rice), **higher-order contracts**
(`contract.secondStage` + `thenCall`, Findler–Felleisen blame), and the
**SPEC §17 / Invariant 9** positioning statement. Deviations from the
research, deliberate: SCIP adoption and a compiler-backed TS adapter are
deferred (the regex PoC now honestly declares its grade instead), and no
container-level eval isolation yet — the hook + signature layers are the
implemented boundary; process/container isolation is the documented next rung.

**PLAN_v6 remaining human items:** Mehar reviews + blesses the goldens (`ent bless refundly.parse_email`, `ent bless refundly.decide`); Mehar records the live H5 session (runbook: `docs/H5_DEMO_RUNBOOK.md`, reset: `scripts/demo_reset.sh`).

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
2. **Live telemetry → Universe** — `ent otel <otlp.json>` reads standard
   GenAI spans (tokens, request/response models) and feeds budgets + the
   model-drift gate; continuous capture (a listening OTLP endpoint, durable
   Parquet/DuckDB by default) is still thin — today ingest is file-at-a-time.
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
6. **Packaging & first-run** — `0.2.0`; wheel + sdist build clean; PyPI
   release wired (Trusted Publishing) but not yet performed; MCP Registry
   `server.json` prepared (see `docs/registry.md`) and blocked only on the
   PyPI release. No binary distribution.

## Explicitly deferred (PLAN_v4 §9)

WebGL renderer · SSE/push steering · presence/multiplayer · `apiVersion` bump +
full mechanical `node`→`unit` rename · advanced retrofit UX.

---

*Keep this current: it exists so the narrative docs have one place to agree with.*
