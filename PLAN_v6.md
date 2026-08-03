# PLAN_v6 — Trust Hardening & Control-Loop Closure

> **Instruction to Claude Code:** This plan consolidates two external audits (frontend/render surface + backend logic). Execute phases strictly in order. Do not begin a phase before the previous phase's acceptance criteria pass. Several audit findings are marked **[VERIFY]** because the auditor could not read the source file — Phase 0 confirms or dismisses them. If a [VERIFY] finding turns out to be already handled correctly, mark it CLOSED in STATUS.md with the evidence (file:line) and skip its fix task. Never weaken an existing test to make a task pass. All work happens on branches; one PR per phase.

**Repo:** https://github.com/akashdatageek/Entiendo.git
**Baseline state:** PLAN_v5 V0–V4 complete, 328 passing tests.
**Goal of v6:** Move from "impressive demo you have to trust the author on" to "a stranger can clone this and rely on the verdicts." Two themes: (A) make the verdicts statistically and mechanically honest, (B) make the control loop enforced and proven live.

---

## Phase 0 — Verify inferred audit findings (½ day)

Open the named files and answer each question with YES/NO + file:line evidence. Record all answers in a new `docs/V6_VERIFICATION.md`. A NO promotes the linked task to confirmed-required; a YES closes it.

| # | Question | File(s) | Linked task |
|---|---|---|---|
| V0.1 | Before applying a proposal diff on approve, is there a base check (git HEAD or per-file content hash recorded at proposal creation, re-validated at apply)? | `src/ent/server.py` | 1.3 |
| V0.2 | Does the claims-boundary check on `apply_edit` resolve symlinks (`os.path.realpath`) and use `os.path.commonpath` against repo root — in BOTH `server.py` and `mcp_server.py`? | `src/ent/server.py`, `src/ent/mcp_server.py`, `src/ent/editloop.py` | 1.4 |
| V0.3 | Is the history append path `flush()` + `os.fsync()` and guarded by a file lock? Does any dedup logic ever rewrite/truncate `events.jsonl`? | `src/ent/history.py` | 3.1 |
| V0.4 | How are secrets excluded from the config sha256 — key-name heuristic, `$ref` markers, or something else? | `src/ent/version.py` | 5.1 |
| V0.5 | Is the Bridge steering-queue write atomic (temp file + `os.rename`)? Is `post_verdict` idempotent? | `src/ent/steering.py`, `src/ent/mcp_server.py` | 3.4 |
| V0.6 | Does `ent ci` run tier1 on blessed goldens, and does a tier1 REGRESSED (exit 1) propagate to the process exit code? | `src/ent/cli.py`, `.github/workflows/ci.yml` | 3.2 |
| V0.7 | Does the health lens color read tier1 stat verdicts (WITHIN_BAND/REGRESSED/UNSTABLE/DEGRADED) or tier0 only? | `src/ent/render.py::build_view`, `src/ent/universe.html` | 2.2 |
| V0.8 | Does `universe.html` already have any live-update mechanism (setInterval poll of an endpoint / version token)? | `src/ent/universe.html`, `src/ent/server.py` | 4.2 |
| V0.9 | Is flow-lens particle animation capped when visible node count grows? | `src/ent/universe.html` | 5.7 |
| V0.10 | Are two overlapping `claims:` globs (two nodes claiming one file) detected and failed, or silently first-wins? | `src/ent/validation.py`, `src/ent/extractor.py` | 3.3 |
| V0.11 | Is tier0/tier1 node execution in-process with no timeout and no resource limits? | `src/ent/testing.py`, `src/ent/evals/runner.py` | 1.1 |
| V0.12 | Are prompt/config bytes hashed raw (no LF normalization)? | `src/ent/version.py` | 5.2 |
| V0.13 | Grep for `except:` and `except Exception: pass` (or `pass`-only handlers) across `history.py`, `tracing.py`, `server.py`, `steering.py`. List every hit. | all | 5.6 |

**Acceptance:** `docs/V6_VERIFICATION.md` exists with 13 answered rows, each with file:line evidence. STATUS.md updated with any CLOSED items.

---

## Phase 1 — P0 backend: honest verdicts, safe writes (2–3 days)

### 1.1 Sandbox the eval runner
The node entrypoint currently runs in-process during tier0/tier1. Isolate and bound it:
- Run each entrypoint in a child process (`multiprocessing` with `spawn` start method, or `subprocess`), input as JSON on stdin, output as JSON on stdout.
- Wall-clock timeout: default 5s tier0, 30s tier1, overridable via manifest `evals.timeoutMs`. On timeout, kill the child, return ERROR verdict `TIER0_TIMEOUT <node>`.
- On POSIX, set `resource.setrlimit` in the child before exec: `RLIMIT_CPU`, `RLIMIT_AS` (default 512MB), `RLIMIT_NOFILE`, `RLIMIT_NPROC`. Skip gracefully on Windows.
- Keep the existing `TIER0_IO_VIOLATION` stub-guard and the restricted-AST invariant evaluator (`invariants.py`) unchanged — this is defense-in-depth on top, not a replacement.
- **Tests:** a fixture node with `while True: pass` → `TIER0_TIMEOUT`, suite does not hang; a node allocating over the limit → ERROR; all existing green nodes still pass; verdict latency for the refundly fixtures stays under 2s per node.

### 1.2 Real statistics in `_stat_verdict`
`runner.py::_stat_verdict` (~line 313) compares a mean delta against a fixed `significance` constant — a threshold, not a test. Replace with a paired bootstrap:
- Store **per-run, per-row scores** in the baseline record at bless/accept time (extend the baseline schema; keep old baselines readable — if per-row scores are absent, fall back to the current threshold logic and tag the verdict `verdictMethod: "threshold-legacy"`).
- New method: per golden row, paired difference `d = s_new − s_base`; paired bootstrap (10,000 resamples over rows, fixed seed for reproducibility) → 95% CI on mean(d).
- Verdict rules: REGRESSED if CI upper < 0; IMPROVED if CI lower > 0; WITHIN_BAND if CI straddles 0 and |mean(d)| ≤ `significance`; UNSTABLE if CI straddles 0 and CI half-width > `significance`.
- Emit CI bounds, n, and the minimum detectable effect at current n with every verdict (CLI output + history event + view model).
- `minRuns` remains a hard floor: refuse to judge below it.
- **Tests (fixed seeds):** injected regression → REGRESSED with CI upper < 0; cosmetic noise → WITHIN_BAND; tiny-n / high-variance → UNSTABLE; legacy baseline without per-row scores → threshold-legacy path still works.

### 1.3 Base-hash guard on proposal apply (if V0.1 = NO)
- At proposal creation: record `base_commit` (git HEAD) and sha256 of current bytes for every file the diff touches; store in the proposal record.
- At approve: re-read each touched file; any hash mismatch → refuse with `proposal stale: <file> changed since proposal created`, write nothing.
- Apply the diff atomically: stage all hunks in memory, write only if every hunk applies with exact context; any failure → abort with zero writes.
- **Tests:** create proposal → mutate a claimed file → approve refused, tree untouched; clean approve still works end to end (extend `tests/test_v4_h5_endtoend.py`).

### 1.4 Single claims authority: `src/ent/claims.py` (if V0.2 = NO or logic is duplicated)
- One function `is_within_claims(repo_root, node, target_path)`: `realpath` the target, `realpath` resolved claim globs, require `os.path.commonpath([target, repo_root]) == repo_root` AND a claimed-path match.
- Route `server.py` apply, `mcp_server.py` `apply_edit`, and `editloop.py` boundary enforcement through this one function; delete duplicate string-prefix checks.
- **Tests:** claim that is a symlink pointing outside the repo → rejected; `../` escape → rejected; legit claimed file → allowed; all three call sites covered.

**Acceptance for Phase 1:** all new tests green + full suite green; `ent eval` on refundly produces tier1 verdicts carrying CI + n; a hostile fixture node cannot hang or escape the runner; a stale proposal cannot be applied.

---

## Phase 2 — P0 control loop: enforced boundary, honest health, live proof (2 days + one manual session)

### 2.1 `PreToolUse` claims hook (deterministic enforcement of Invariant 8)
- New file `.claude/hooks/enforce_claims.py`: fires on matcher `Edit|Write|MultiEdit`; reads `tool_input.file_path`; resolves the owning node from `entiendo/graph.json` claims (reuse `claims.py` from 1.4 — do not reimplement); returns `permissionDecision: "deny"` with a message naming the owning node when the path is unclaimed or outside the currently-steered node's claims ("currently steered" = the active item in the Bridge steering queue; if no steer is active, deny only unclaimed files).
- Register the hook in `.claude/settings.json` so it is active in this repo, and in the plugin manifest (task 4.3).
- Deny message must be actionable: name the file, the owning node (or "unclaimed"), and the fix (`steer this node first` / `add the file to a node's claims and re-extract`).
- **Tests:** a script-level test invoking the hook with a JSON payload for (a) unclaimed file → deny, (b) file owned by a non-steered node while a steer is active → deny, (c) file inside the steered node's claims → allow.

### 2.2 Health lens reads tier1 significance (if V0.7 = tier0-only)
- In `build_view()`: attach each node's latest tier1 `statVerdict` + CI + n (from history) to the node view.
- In `universe.html` health-lens coloring: blend tier0 verdict with tier1 significance — WITHIN_BAND = calm green; REGRESSED = signal red ring; DEGRADED = amber ring; UNSTABLE = amber pulse; tier0 RED always wins. Legend line: "red only on statistically meaningful movement."
- Dossier shows the CI and n next to the verdict so "within band" is visibly a first-class state.
- **Tests:** `build_view()` output includes `statVerdict`/CI for a node with tier1 history (Python test); rendering assertion deferred to 4.1's Playwright suite but add the data-contract test now.

### 2.3 Bridge integration test with a real MCP client (no hardcoded diff)
- New `tests/test_h5_live_bridge.py`: boot `ent serve` on a scratch copy of `examples/refundly`; enqueue a steer through the Bridge queue; drive the MCP tools in sequence as a real client would — `await_steering` → `get_node_context` → `apply_edit` (content generated by the test from the returned context, not a pre-stored diff) → `post_verdict` — and assert a proposal is created, visible via `GET /api/proposals`, and approvable; approve it and assert the file changed and a history event was appended.
- This is the automated stand-in for the live loop; it must exercise the same seams the live session will.

### 2.4 The live H5 run — **manual, Mehar drives**
Claude Code prepares; Mehar executes. Preparation tasks:
- Refresh `docs/H5_DEMO_RUNBOOK.md` against the current code: exact commands, expected screen states per step, a reset section (`git checkout -- examples/refundly && ent extract`), and a note that steering `refundly.gateway` yields tier0 `UNTESTED` (external node — expected, not a failure).
- Add `ent demo-reset` (or a make target) that restores the scratch fixture in one command.
- **Exit condition (manual):** one uncut recording of steer → Claude Code edit via MCP → diff in the Universe → approve → tier0 verdict, in a live session. Until this exists, STATUS.md keeps the residual open.

**Acceptance for Phase 2:** hook denies an out-of-claims `Edit` in a real Claude Code session (verify by hand once); bridge integration test green; health lens color demonstrably driven by significance data; runbook executable top to bottom.

---

## Phase 3 — P1 durability & CI truth (2–3 days)

### 3.1 JSONL append durability (if V0.3 = NO)
- `history.py`: append = one JSON line via `open(path, 'a')` + `flush()` + `os.fsync()`; whole append under `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows).
- If any dedup currently rewrites the file: replace with append-only writes + read-time "latest wins" fold. `events.jsonl` is never truncated or rewritten.
- Add an event schema `v` field (integer, start at 1) to every new event for future migrations; readers tolerate its absence on old events.
- **Tests:** two processes appending concurrently → no truncated/interleaved lines (parse every line); dedup fold still produces the same timeline the UI expects.

### 3.2 `ent ci` composition (if V0.6 = NO)
- `ent ci` runs in order: `validate` → `extract --check` → tier0 all nodes → tier1 on blessed goldens. Process exit = max severity across steps per the phase7 table (0 pass/within-band, 1 RED/REGRESSED, 2 ERROR, 4 UNSTABLE/DEGRADED). Advisory (unblessed) tier1 never blocks.
- Update `.github/workflows/ci.yml` accordingly.
- **Test:** fixture repo with an injected golden regression → `ent ci` exits 1; UNSTABLE-only → exits 4; clean → 0.

### 3.3 Overlapping-claims detection (if V0.10 = NO)
- After resolving all claims globs to realpaths, build `file → [node_ids]`; any file with >1 claimant → validation error naming the file and all claimants; non-zero exit in both `ent validate` and `ent extract`.
- **Test:** two manifests with overlapping globs → validate fails with both node ids in the message.

### 3.4 Write-path hardening: CSRF + atomic queue (if V0.5 = NO)
- `server.py`: bind 127.0.0.1 only; every state-changing POST requires Origin/Referer `http://127.0.0.1:<port>` + a per-session CSRF token minted at page render; reject otherwise (403 with explanation).
- `steering.py`: queue items written to temp file + `os.rename` (atomic); consumption moves the item into an `in-progress/` dir via rename so two operator agents cannot double-take; `post_verdict` idempotent via a verdict id (duplicate → no-op, logged).
- **Tests:** double-consume race (two consumers, one item → exactly one wins); duplicate `post_verdict` → single history event; POST without token → 403.

### 3.5 Extractor honesty about blind spots
- Add a heuristic pass over claimed files flagging `importlib.import_module` / `__import__` / `getattr`-dispatch / `subprocess` / `requests|httpx|urllib` usage → emit `possibleUndeclaredDynamicDep` warnings into `graph.json` (named per node), surfaced in the dossier and `ent extract` output.
- Tag all TS-extractor-verified edges `verificationSource: "ts-poc"` until a real tokenizer lands; render them at declared-grade styling.
- Document the blind-spot list in `docs/multi-language.md`: absence of an edge is not proof of no dependency.
- **Test:** fixture file using `importlib.import_module` → warning present in `graph.json` naming the node.

**Acceptance for Phase 3:** all Phase 3 tests green; kill -9 during an append leaves `events.jsonl` parseable; CI provably fails on a golden regression.

---

## Phase 4 — P1 shippable `ent dev` (3–4 days)

### 4.1 Frontend test harness (currently zero tests touch the render JS)
- Add Playwright (kept out of the default pytest run; new `ent ci --with-frontend` step or separate workflow job): load a generated `universe.html` over the refundly fixture and assert — each of the six lens buttons changes canvas/legend state; trace playback advances hops sourced from `events.jsonl`; timeline scrub changes the displayed fingerprint band; Approve/Reject POST to the correct endpoints and the dossier updates; empty-repo render shows the `ent init` invitation.
- Keep it small: ~10 tests covering the six lenses + the two write flows + empty state. This is a regression net, not coverage theater.

### 4.2 File-watch + live reload (if V0.8 = NO)
- `ent serve` watches `**/entiendo.node.yaml`, claimed files, and `entiendo/history/*` (stdlib mtime polling is fine; `watchdog` optional); on change, re-run extract + `build_view`, bump a version token served at `/api/version`; the page long-polls the token and reloads on change.
- Debounce (500ms) so a burst of writes triggers one rebuild. Extract failure → keep serving the last good view + show a drift banner with the error text (never a blank screen).
- Rename/alias the command `ent dev` (keep `ent serve` as alias) to match the packaging story.

### 4.3 Claude Code plugin packaging + MCP elicitation approval
- Add `.claude-plugin/plugin.json` (+ `marketplace.json`) bundling: the `ent mcp` server, the `entiendo-operator` skill, and the `enforce_claims` hook from 2.1. Installing the plugin in a fresh repo must activate all three with no manual copying.
- Add an MCP elicitation path: when `post_verdict` targets an approval-gated node (`approval.required: true`), the server elicits approve/reject from the operator inside the Claude Code session (MCP elicitation, 2025-06-18 spec). Web-UI approval remains; whichever answers first wins, the other is invalidated idempotently (uses 3.4's verdict id). If the connected client does not support elicitation, fall back to the Bridge/web flow with a clear message.
- **Tests:** plugin manifest validates; elicitation path unit-tested with a mock client; fallback path tested.

### 4.4 tier1 golden for `refundly.decide` (flagship agentic unit)
- Build a stub harness that serves `decide`'s neighbours (`order_lookup`, `read_policy`, `issue_refund`, `write_ledger`) from recorded trace fixtures so `decide` runs in isolation.
- Author `evals/refundly.decide/golden_v3.jsonl` with boundary cases: amounts at policy thresholds, ambiguous fraud signals, partial-refund edges. Target a baseline in the 0.75–0.92 band (must discriminate — the injected-regression test from 1.2 must fire on it). All rows `humanBlessed: false` — **Mehar blesses manually via `ent bless`** (the plan must not bless; that would recreate the bootstrapping trap).
- **Tests:** harness runs `decide` standalone; injected regression on `decide` → REGRESSED.

**Acceptance for Phase 4:** fresh `git clone` + install + `ent dev` gives a live-reloading Universe; plugin installs into a clean Claude Code project and the hook + MCP + skill all activate; Playwright suite green; `decide` has a discriminating (unblessed, pending-Mehar) golden.

---

## Phase 5 — P2 polish (as time permits; nothing here blocks launch)

- **5.1 Secret exclusion review** (per V0.4 finding): if exclusion is a key-name heuristic, extend it — exclude values matching common secret patterns (entropy check or key regex `(?i)(secret|token|key|password|credential)`), and document the mechanism in SPEC. Never let an unexcluded secret reach any rendered or logged surface.
- **5.2 Fingerprint stability:** hash claimed-file **blob content** (git blob shas or direct sha256) instead of commit sha for the `code` dimension, so rebases/squashes with identical content do not churn composites or falsely reset edge-verification staleness. Migration: recompute fingerprints once, record a `version` event noting the method change.
- **5.3 LF normalization** before hashing prompt/config bytes (kills cross-OS fingerprint churn). Combine with 5.2's one-time recompute.
- **5.4 Budget honesty:** "p95 over 5 runs" is effectively max — either widen the measurement window (use all recorded trace hops for the node, not just the current eval batch) or rename the displayed label to `max(minRuns)` until a real window exists.
- **5.5 Replace string-assertion tests** (e.g. asserting `bless.py` contains no `environ`) with behavioral subprocess tests; delete the string asserts.
- **5.6 Bare-except sweep** (from V0.13 hit list): each hit → log + re-raise, or a narrow expected-exception type with a comment. History/tracing writes must never silently drop.
- **5.7 Canvas performance cap:** when visible nodes > 100, cap flow-lens particles (e.g. 1 per edge, no glow) and skip offscreen edges; keep WebGL deferred until 150-visible actually hurts.
- **5.8 Accessibility mirror:** offscreen semantic list (Figma Mirror-DOM pattern) syncing node selection two-way; ARIA live region announcing lens changes and verdicts.
- **5.9 Stale-graph guard:** `ent render`/`ent dev` warn when `graph.json` mtime predates any claimed file or manifest mtime ("map may be stale — run ent extract"), unless file-watch (4.2) makes this moot.
- **5.10 Legacy history hygiene:** dossier renders pre-V3 `blessedBy: "unknown"` records as "unverified historical blessing" (append-only history is never rewritten).

---

## Sequencing summary & exit conditions

| Phase | Theme | Exit condition |
|---|---|---|
| 0 | Verify | 13 questions answered with evidence in `docs/V6_VERIFICATION.md` |
| 1 | Honest verdicts, safe writes | Sandbox + bootstrap-CI verdicts + apply guard + one claims authority, all tested |
| 2 | Enforced & proven control | Hook denies out-of-claims edits; bridge test green; **live H5 recording exists (Mehar, manual)** |
| 3 | Durability & CI truth | Concurrent-append safe; `ent ci` fails on golden regression; queue atomic |
| 4 | Shippable `ent dev` | Clone → install → live-reloading Universe; plugin installs clean; frontend regression net |
| 5 | Polish | Opportunistic |

**Two things Claude Code must NOT do:** (1) bless any golden dataset (`humanBlessed` is Mehar's act alone — propose rows, never bless); (2) rewrite or truncate `entiendo/history/events.jsonl` for any reason.

**Definition of done for v6:** a stranger clones the repo, runs `ent ci` and `ent dev`, installs the plugin, and every verdict they see — coverage, drift failure, tier0, tier1 with CI bounds, verified edges with source grades, blessed baselines with real identities — is one they can justify trusting, and an out-of-claims agent edit is mechanically impossible in a hooked session.
