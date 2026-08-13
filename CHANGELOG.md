# Changelog

All notable changes to Entiendo. Versioning follows [SemVer](https://semver.org)
(0.x: minor bumps may break, patch bumps never do).

## Unreleased

### Added
- **The steering bridge: `ent ci --enqueue-failures`** (astrobee gap 6, the
  design answer to "why doesn't Entiendo take help of the builder?"). Red
  verdicts used to be report lines, and report lines cannot be delegated.
  Each RED/ERROR unit now becomes ONE structured steering task the operator
  loop consumes through the normal Bridge (`await_steering` → edit through
  the unit → `post_verdict`): the diagnosis, then mechanical options ranked —
  declare `contract.requires` (with the missing module parsed from the
  error), repoint the entrypoint at a probed importable candidate, or fix a
  genuine defect. Idempotent (one live task per unit; a consumed task can
  re-queue if the unit is still red). The separation holds the whole way:
  the judge diagnoses and delegates, never edits, and every task carries an
  explicit prohibition on golden authorship — the builder must not write
  the answers it is graded against (SPEC §17).
- **`ent amend`** (astrobee gap 5): sideEffects contradictions become staged,
  reviewable amendments instead of notes that scroll away. `ent amend` lists
  every unit declaring `sideEffects: none` whose claimed files hit an
  effect-implying construct (subprocess / requests / httpx / urllib and the
  JS counterparts — dynamic-import and getattr stay visibility notes, not
  effects), with per-file evidence; `ent amend --accept <id>` applies ONE
  unit's `none → external` flip as a minimal text edit (comments survive).
  One at a time on purpose: dogfooding flagged 5 of our own units — four
  were true (sandbox children, git shells, pytest runs) and accepted, and
  one (`ent.graph`) is a false positive (the extractor's own regex table
  contains the words it scans for) — exactly the case that proves a contract
  change needs a human eye, so it stays staged, unaccepted, documented.
- **Coverage tells both truths** (astrobee gap 4): `coverage.json` now
  separates the universes — a `recognized` block (files a language adapter
  can parse for edges, with its own coverage figure) and
  `unmappedByExtension` (counts of files beyond every adapter, biggest hole
  first). `ent extract` prints one headline stating both numbers ("7% of
  2,695 · 100% of 195 adapter-recognized · 2,500 beyond every adapter (.cc
  474, …)") instead of the scarier one alone, caps the unaccounted listing
  at 20 with the remainder counted (never a silent cap), and the Universe
  summary shows "coverage 7% (100% of 195 recognized)".
- **Repo-wide Python package map** (astrobee gap 3): `import X` now also
  resolves through the importing file's own directory (script-style
  sys.path) and a cached map of top-level packages living anywhere in the
  tree (catkin/src layouts — `localization/…/scripts/localization_common`
  answers `import localization_common`). astrobee mapped with ZERO edges
  before this; by-name monorepo imports were invisible, and a missing edge
  that looks like decoupling is the worst kind. Ambiguous names (two dirs,
  one package name) are refused, never guessed — declared in
  `capabilities().cannotResolve`. Dogfood catch: the resolver immediately
  surfaced `ent.plugin → ent.packaging` (`enforce_claims.py` does
  `from ent import claims`), undeclared until now.
- **`contract.requires` + ENV-BLOCKED verdict** (astrobee gap 2): a unit can
  declare the runtimes its entrypoint needs (`requires: [rosbag, tf]`).
  When one is missing here — checked with `find_spec`, never executed — the
  eval yields **ENV-BLOCKED** instead of ERROR: exit 0, counted separately
  in `ent ci` ("N env-blocked (requires a runtime absent here — not
  failures)"), grey on the map, sorted with the informational states in the
  Universe summary. "The judge is in the wrong environment" and "the unit is
  broken" are different facts; an *undeclared* missing import still reads
  ERROR — the conflation is only ever resolved by declaring it.
- **Retrofit probes candidate entrypoints before proposing them** (astrobee
  gap 1): every candidate is import-checked in a bounded child (rlimits +
  wall clock, same loader as the eval judge), and a proposal only carries an
  entrypoint that actually imports in this environment. Candidates that need
  an absent runtime (astrobee shipped five whose entrypoints import ROS
  packages) fall through to the next importable candidate or produce a
  `no importable entrypoint in this environment` note instead of a fake
  ERROR at eval time. `ent retrofit --no-probe` restores the fast blind
  guess. `ent.retrofit` now honestly declares `sideEffects: external` —
  the effect probe caught the subprocess spawn the moment it landed.

### Fixed
- **Three more defects from the famous-105 gauntlet** (react, cpython,
  kubernetes, babel, next.js and 100 friends): the **accept-time reflex eval
  now runs in the bounded sandbox child** instead of in-process — node.js
  ships a python script that argparses and `sys.exit()`s at import, which
  used to kill the accept command and, worse, executed unvetted repo code
  with no rlimits or wall clock; a nameless specifier (`'/'`, webpack)
  crashed the TS resolver's `with_suffix`; unreadable claimed files
  (vanished/broken paths, spring-boot flavour) now yield no imports instead
  of an OSError.
- **Three defects found by running Entiendo against 100 real repositories:**
  (1) accepting one retrofit proposal whose inferred deps pointed at staged
  siblings left a dangling `unknown node` edge, breaking the partial project
  on 15/94 repos — edges to not-yet-accepted units are now **held back** and
  reported, and the reconciler re-raises the real edge as drift once the
  sibling is accepted (nothing forgotten, nothing broken); (2) a symlink
  escaping the repo root (jekyll ships one pointing at `/etc/passwd`)
  crashed every walk — escaping symlinks are now skipped, never followed,
  never fatal (in-root symlinks still count); (3) unstat-able entries
  (trpc's ENAMETOOLONG fixtures, symlink loops) aborted retrofit — per-entry
  OS errors now skip-and-continue, and the TS adapter treats garbage
  specifiers matched inside template strings as resolving to nothing.

### Added
- **Evaluability grades** — three states instead of one smear of UNTESTED
  red. Every unit now carries `evaluability`: **ready** (takes values, no
  effects beyond its declarations, statically clock-clean — only ground
  truth is missing: "awaiting goldens/blessing", a data chore, not a design
  problem), **evaluable-after-refactor** (I/O fused with the logic — reads
  the clock, talks to the world with no declared edge to stub; `ent extract`
  fires the law at build time with the split named, before the code
  hardens), or **interior** (documented, never contracted). The health lens
  paints untested-but-ready **blue**, needs-refactor amber, interior grey;
  the window answers "Can it be judged?" in plain words; the system summary
  counts the three states; `ent new` births units as "ready (probed) —
  awaiting goldens", not "untested". Honesty: the grade is always evidence —
  `(probed)` or `(static)`, never "verified" (the probe only observes the
  paths it executes; the grade upgrades as real fixtures arrive).

## 0.2.0 — 2026-08-12

The first published release. Everything from the 2026-08-04 beta cut (below)
plus two research-adaptation rounds and the trust-hardening plan.

### Added
- **OTel GenAI span reader** (`ent otel <otlp.json>`): ingest
  `gen_ai.usage.input_tokens`/`output_tokens` and
  `gen_ai.request.model`/`gen_ai.response.model` from the spans standard
  auto-instrumentation (OpenLLMetry/OpenLIT style) already emits — read, never
  proxied, so the read-only invariant holds. Nested LLM spans roll up to the
  enclosing unit via `entiendo.node_id` or `observability.spanName`.
- **Budgets now gate**: `tokensPerCall`/`costPerCallUsd`/`p95LatencyMs` were
  declared but never enforced. `ent ci` gains a budgets stage — over budget is
  DEGRADED (exit 4). refundly's deliberate gateway overage is now asserted in
  CI as the proof the gate works.
- **Higher-order contracts** (`contract.secondStage`) — the Findler–Felleisen
  wrap-and-defer pattern for factory units (compile()/match factories,
  configured closures), whose first-stage output cannot be judged eagerly.
  Fixture rows invoke the returned callable via `thenCall: [{input,
  expect?}]`; the deferred contract judges each invocation **with blame**: a
  `domain` violation blames the caller (broken fixture → eval ERROR, the
  unit is not at fault), a range violation blames the unit (→ RED). A
  declared second stage whose first stage returns plain data is RED outright.
- **Effect probe in the eval sandbox — evaluability as graded evidence.**
  The sandboxed child installs an audit hook and records the unit's observed
  effects (fs-write / network / subprocess; interpreter cache, OS tempdir and
  the plane's own journal excluded as runtime noise). Only the sound
  direction gates: `sideEffects: none` plus an observed effect is a
  demonstrably false contract → **RED**, with the effect named. Observing
  nothing reports "no effects observed under probe" — an evidence grade,
  never a verified invariant (Rice's theorem; the note is in the artifact).
  First catch on landing: `ent.surface` declared `none` while `build_view`
  shells out to git for the commit axis — now honestly `external`.
- **Adapter capability manifests + per-edge resolution grades** — the honest
  boundary of the closed-world guarantee. Every language adapter declares its
  blind spots (`capabilities()`: grade `ast`/`regex-poc`/`compiler`, evidence
  tag, named `cannotResolve` constructs); the graph publishes them
  (`graph.adapters`), every edge carries `resolution:
  complete|partial|none`, and `ent doctor` prints "what the map cannot see".
  "Verified, not inferred" collapses exactly where resolution is partial —
  so the holes are declared machine-readably, never hidden.
- **Test-case extraction** (`ent import-tests <path> [--method
  ast|collect|both]`): mine an existing pytest suite into case files under
  `entiendo/proposals/imported-tests/`. The AST path never executes repo
  code and never emits an evaluated value (computed parametrize lists are
  counted-skipped); the collection path (`pytest --collect-only` + a
  plugin, module import only — sandbox for untrusted repos) resolves
  computed and fixture params; whatever cannot be represented faithfully is
  a flagged `needs_harness` entry. The coverage line ("extracted N of M…")
  is always printed — gaps are visible, never hidden.
- **Clock-dependency detector** (`ent detect time [unit…]`): `time_pure`
  becomes a reported component *property*, never a test failure. The static
  pass (AST) flags `datetime.now`/`date.today`/`time.time`/`uuid.uuid1`/
  unseeded `random`/`os.environ['TZ']` and propagates transitively through
  an intra-project call graph (a unit calling a clock-touching helper two
  files away is flagged, with the chain as evidence). The dynamic pass
  (`.[detect]`, time-machine) replays smoke fixtures under shifted clocks —
  +1d/+180d/+1y, a DST boundary, Feb 29, a TZ flip, and a 12-step month
  sweep so a seasonal `month == 12` branch is always crossed — and any
  output delta is `time_pure: false` with the failing shift named. Units
  time-machine cannot intercept (C extensions, subprocesses) are
  `time_check: incomplete` with libfaketime documented as the escalation
  path. Harvested fixtures now record `capturedAt` so drift is attributable.
- **The Bash bypass hole is closed with detect-and-revert.** Predict-and-block
  on shell strings is unwinnable (`python -c`, `sed -i`, `tee`, heredocs,
  `git checkout <sha> --` all rewrite files without an editor tool), so a
  **PostToolUse hook on Bash** (stdlib-only, works pre-install in a fresh
  clone) recomputes every root's goldens against its lock after each shell
  command: mismatches are restored from HEAD, rogue untracked goldens are
  deleted, and the agent gets the warning on stderr (exit 2).
  `ENTIENDO_BLESS_IN_PROGRESS=1` lets a human re-bless flow through.
  `.claude/settings.json` additionally carries `permissions.deny` rules for
  golden paths and the lock (deny rules hold even in
  `--dangerously-skip-permissions`), the PreToolUse matcher gains
  NotebookEdit, and `ent lock --os` (chattr/chflags, `--undo` counterpart)
  offers the only true pre-execution block where privileges allow.
- **Repo-wide golden hash manifest** (`entiendo/goldens.lock`): SHA-256 of
  every golden file — datasets manifests declare *plus* anything matching
  `evals/**/golden*`, so a planted-but-undeclared golden is caught as an
  addition. `ent goldens verify` (exit 1 on mismatch, `--require-lock` for
  opted-in repos), `ent goldens bless` (loud, refuses under CI — the gate
  cannot re-pin itself), tier-1 grading refuses tampered ground truth
  (ERROR, never a pass), a required `integrity.yml` workflow, and the lock
  itself joins the hook's oracle deny-list. `SECURITY.md` documents the
  model, its limits, and the Sigstore upgrade path.
- **Golden rows carry oracle-class provenance** — the tautological-oracle
  guard. Every golden row may declare `oracleClass`: `contract-derivable`
  (the expected value follows from the spec alone) or
  `implementation-derived` (captured from the code's own output — a value
  that can never disagree with it). `ent bless` prints the census and
  **refuses** to bless a dataset containing implementation-derived rows
  unless the human passes `--accept-implementation-derived`; rows harvested
  by `ent fixtures` are tagged implementation-derived by construction;
  refundly's spec-first goldens are tagged contract-derivable.
- **The oracle boundary is mechanical**: the `enforce_claims` hook now
  fail-closes on the verifier's own state — `entiendo/history` (the append-only
  record), `entiendo/baselines` (baselines + blessing signatures),
  `entiendo/steering` (verdicts enter via `post_verdict`), the generated
  `graph.json`/`coverage.json` (Invariant 1, now enforced at the keystroke),
  and any **human-blessed golden dataset**. Agents demonstrably game evals by
  editing the evaluator's state; the proposer being *mechanically unable* to
  touch the oracle is the propose-verify separation the reward-hacking
  literature calls non-negotiable. Writes that bypass the hook still void the
  blessing's content signature — both layers are adversarially tested.
- **MCP Registry readiness**: `server.json` at the repo root (official
  registry schema, `io.github.akashdatageek/entiendo`), an `entiendo` console
  script alias so `uvx entiendo` works, the PyPI ownership marker embedded in
  the README, and `docs/registry.md` — the one-command publish checklist for
  the day the package lands on PyPI. Tests keep the versions and markers from
  drifting apart before then.
- **Model-drift enforcement**: the manifest pins a model (`version.model`);
  the OTel reader records what actually answered (`gen_ai.response.model`).
  A silent model swap now fails `ent ci` (severity 1) until the human fixes
  the app or accepts the swap with `ent pin` — which moves the composite
  fingerprint, so an accepted swap is a diffable version, not a silenced
  alert. Prefix matching is one-way: a pin of `claude-sonnet-5` accepts its
  dated forms; a dated pin accepts nothing looser.
- **Layered map by default**: the Universe now opens on a left-to-right
  layered DAG (callers left, foundations right, per-layer labels in plain
  words) instead of the constellation scatter — the constellation remains a
  toggle. Press `f` (or the button in a unit's impact tab) to focus the
  **cone** of one unit: everything it depends on and everything that depends
  on it; the rest of the map fades.
- **The first manifest pays rent immediately**: `ent retrofit --accept` now
  regenerates the map, reports the accepted unit's edges, and runs its reflex
  eval in the same command — value on the spot, not a homework list. Partial
  coverage is pinned as a first-class state: one manifest in a many-file repo
  validates, extracts, evals and passes `ent ci`, with every undeclared file
  named (never silently partial).
- **`interior.steps`** — a unit's window can now tell the story of *how it
  works, in order*: named steps typed by the OTel GenAI span kinds
  (`chat`/`execute_tool`/`invoke_agent`/`embeddings`/`workflow`, rendered as
  plain words), each optionally bound to a file at a content hash. Editing a
  bound file makes the step **stale — a drift-class reconciliation error that
  names the new hash**, so the description cannot silently rot (the Swimm
  model). A step that `crosses` into another unit must match a declared edge.
- **`contract.harness`** — the seam for units whose entrypoint is not a
  one-argument function. A harness is called as `harness(row, ctx)` with
  `ctx.entrypoint`/`ctx.root`/`ctx.node` and returns the output that invariants
  judge, so `f(node, root)`, `f(root, node_id)`, zero-argument functions and
  class-based APIs can be evaluated. Harnesses live under `evals/` and are never
  claimed, so they stay out of composite fingerprints. This took Entiendo's own
  map from 5 runnable units to 14.
- **Self-hosting**: the Entiendo repo now manages itself — 14 semantic units
  under `units/` with real contracts, reconciler-verified edges, and (with the
  harness seam above) a runnable tier0 eval each. CI gates the repo's own map
  like any other project.
- The `enforce_claims` hook honors **explicitly-unclaimed** files: globs in
  `entiendo/unclaimed.txt` (a repo's tests, docs, scripts) stay editable,
  including new files matching an acknowledged pattern. Truly unclaimed files
  are still denied.

### Fixed
- All file walks (coverage, retrofit candidates) stop at nested project roots
  via one shared `iter_project_files` — previously only manifest discovery did.
- The eval sandbox shields its stdout JSON protocol from entrypoints that
  print (found running `ent.cli`'s own smoke — a CLI that prints corrupted the
  verdict channel).
- Manifest discovery stops at nested project roots (a subdirectory with its
  own `entiendo/` control plane or its own `.git`): their claims resolve
  against *that* root, so sweeping them into a parent walk misrooted every
  claim — `ent validate` at the Entiendo repo root failed on its own examples,
  which in turn made the Claude Code plugin's MCP server refuse to start.
- `ent mcp` starts on an unmanaged repo (zero manifests) — that is the
  retrofit starting state, not an invalid one. Actually-invalid manifests
  still exit 2 without `--allow-invalid`.

### The beta cut — 2026-08-04

Everything below shipped since the 0.1.0 scaffold, across
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
