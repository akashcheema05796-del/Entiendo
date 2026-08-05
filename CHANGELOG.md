# Changelog

All notable changes to Entiendo. Versioning follows [SemVer](https://semver.org)
(0.x: minor bumps may break, patch bumps never do).

## 0.2.0 — 2026-08-04

First public beta. Everything below shipped since the 0.1.0 scaffold, across
PLAN v4 (the Universe), PLAN v5 (close the loop), and PLAN v6 (trust
hardening); 389 tests plus an optional 11-test Playwright browser suite.

### The map
- The Universe: a six-lens canvas (structure / flow / trace / health /
  timeline / blast radius) rendered from the generated graph — celestial
  cartography with dossiers, search, keyboard nav, minimap, trace playback,
  and timeline scrubbing.
- `ent serve` (live) and `ent render` (static snapshot) share one template;
  `ent dev` adds live reload (mtime watcher, `/api/version` long-poll,
  last-good view + drift banner when the tree breaks mid-edit).
- Scale honesty: particle caps past 100 units, offscreen skip.

### Trust hardening (PLAN v6)
- Sandboxed eval runner: child process, wall-clock timeouts
  (`TIER0_TIMEOUT`), POSIX rlimits (gracefully skipped where unsupported).
- Paired-bootstrap tier1 verdicts: 95% CI over per-row score deltas, 10k
  resamples, fixed seed; `REGRESSED` only on statistically meaningful
  movement; underpowered runs read `UNSTABLE`; legacy baselines tagged
  `threshold-legacy`.
- Single claims authority (`ent.claims`): realpath + containment + resolved
  claims, routed through every write path; symlink-out claims void.
- `enforce_claims` PreToolUse hook: out-of-claims edits mechanically denied
  in managed repos (fail-open outside them); shipped in the Claude Code
  plugin.
- Proposal base-hash guard: approving a stale proposal (tree moved since it
  was created) refuses with zero writes.
- Durable history: the append-only event log is written under an exclusive
  lock (`fcntl.flock`, `msvcrt` fallback) with `fsync`, `seq` computed under
  the lock, `v: 1` schema field. Never rewritten, never truncated.
- Atomic steering: `O_CREAT|O_EXCL` claims (exactly one consumer wins),
  idempotent verdicts/proposals (`{duplicate: true}`).
- HTTP hardening: loopback-only bind, per-process CSRF token required on all
  POSTs, threading server.
- `ent ci`: one gate with severity exit codes (0 pass · 1 RED/REGRESSED ·
  2 ERROR · 4 UNSTABLE/DEGRADED, max across stages) including a tier1 stage
  on BLESSED goldens only — unblessed datasets are advisory and never block.
- Extractor blind-spot honesty: dynamic constructs static analysis cannot
  see (`importlib`, `__import__`, getattr-dispatch, subprocess, HTTP
  clients) are flagged as `possibleUndeclaredDynamicDep` warnings;
  TypeScript-PoC edges carry `verificationSource: "ts-poc"` and render
  declared-grade.
- Hashing honesty: secret config values never enter the composite (key
  contributes, value doesn't); CRLF→LF normalisation for prompt/config so
  Windows checkouts mint no phantom versions.

### The control loop
- The Bridge: file-based steering queue; `ent serve --operator` +
  `entiendo-operator` skill turn Claude Code into the steered workload
  (await → scoped context → claims-confined edit → verdict).
- Approval, for real: gated units land edits as proposals (diff-first, tree
  reverted until a human approves in the Universe); MCP elicitation can
  settle the approval in-line with graceful web fallback.
- Blessing with teeth: `humanBlessed` is a content signature; datasets
  changed since blessing run advisory; blessing requires an interactive TTY
  and a real identity — CI cannot bless, and no env var bypasses it.
- Runtime verification (V1): declared edges flip to verified from recorded
  spans, expire on drift; `verificationSource` / `observationCount` /
  `lastVerifiedAt` on every edge.

### Distribution
- Claude Code plugin (`.claude-plugin/`): MCP server, operator skill,
  claims hook.
- Packaging fix: the manifest schema now ships inside the wheel — a clean
  `pip install entiendo` works outside a checkout (quickstart measured at
  under one minute to first Universe).
- Apache-2.0 LICENSE; CI adds dependency audit (pip-audit) + CycloneDX SBOM.

## 0.1.0 — 2026-07

Initial scaffold: manifests + JSON-Schema validation (L0), extractor /
reconciler with generated `graph.json` + `coverage.json` (L1), `@ent.node()`
instrumentation (L2), append-only history (L3), tiered evals (tier0 reflex /
tier1 golden / tier2 judge scaffold), and the first render surface.
