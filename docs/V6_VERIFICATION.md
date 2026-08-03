# PLAN_v6 Phase 0 — audit-finding verification

Read-only pass answering the 13 [VERIFY] questions with file:line evidence.
A **NO** promotes the linked task to confirmed-required; a **YES** closes it.
(Two questions — V0.11, V0.12 — are phrased inverted: there a YES *confirms* the
problem; the Verdict column states the task disposition explicitly.)

| # | Question | Answer + evidence | Verdict → linked task |
|---|---|---|---|
| V0.1 | Base check before applying a proposal on approve? | **NO** — `steering.py:218-231` `approve()` blind-writes each stored `after` (`(root/rel).write_text(d["after"])`, line 225); no `base_commit`, no per-file hash recorded at `propose_from_outcome` (`steering.py:169-202`) or re-validated at apply. | **1.3 REQUIRED** |
| V0.2 | Claims check resolves symlinks + uses `commonpath` in both servers? | **NO** — `mcp_server.py:107-108` is a string set-membership (`Path(entry["path"]).as_posix() not in claims`); no `realpath`, no `commonpath`. `editloop.py:131-148` `check_boundary` normalizes via `resolve().relative_to(root)` (line 145) but also ends as set-membership; claim paths themselves are never realpath'd (a claim that is a symlink out of the repo is not caught). Logic exists in ≥3 flavours (`agent.py:139` too). | **1.4 REQUIRED** |
| V0.3 | Append fsync'd + locked? Does dedup rewrite `events.jsonl`? | **Half NO** — `history.py:51-58` `_append` is `open("a")` + write, **no `flush()`/`os.fsync()`/lock**; also re-reads the whole file per append for `seq` (line 53). **Dedup never rewrites**: `append_version` (`history.py:74-97`) skips the write when the composite is unchanged — decision-at-write, file never truncated. Append-only holds. | **3.1 REQUIRED** (fsync+lock+`v` field; the "replace rewrite-dedup" half is already satisfied) |
| V0.4 | How are secrets excluded from the config sha256? | **They aren't, mechanically** — `version.py:59-84` hashes **raw bytes of every claimed config file** (`path.read_bytes()`, line 72). Exclusion is purely conventional: secrets are expected to be reference-only (Invariant 6) and un-claimed. The hash is one-way (nothing rendered), but an in-file secret does reach the hash input. | **5.1 REQUIRED** (document + heuristic) |
| V0.5 | Queue write atomic? `post_verdict` idempotent? | **NO** — `steering.py:58` enqueue is a plain `open("a")` append (no temp+rename). `claim_next` (`steering.py:91-104`) has a TOCTOU race: `_is_claimed` check (line 100) then marker write (line 102) are not atomic — two pollers can both pass the check. `post_verdict` (`steering.py:123-131`) overwrites `results/<id>.json` — last-wins, no duplicate history event, but no verdict-id no-op either. | **3.4 REQUIRED** |
| V0.6 | Does `ent ci` run tier1 on blessed goldens with exit propagation? | **NO** — `ci.py` runs validate → reconcile (→ coverage) → **tier0 only** (`_eval_stage` calls `run_tier0`, `ci.py:~95`); no `tier1`/`golden` reference anywhere in `ci.py` or `.github/workflows/ci.yml` (grep: zero hits). | **3.2 REQUIRED** |
| V0.7 | Health lens reads tier1 stat verdicts? | **tier0-only** — `render.py:18` imports only `run_tier0`; `build_view` health = `run_tier0(...).verdict` (`render.py:46`); no `statVerdict`/CI in the view model or `universe.html`. | **2.2 REQUIRED** |
| V0.8 | Any live-update mechanism in `universe.html`? | **NO (global)** — the only poll is the steer-result poll (`universe.html:870` `startSteerPoll`, scoped to one steering request). No `/api/version` token, no view reload on change. | **4.2 REQUIRED** |
| V0.9 | Flow-lens particles capped at scale? | **NO** — `seedParticles` (`universe.html:351-353`) allocates 2–3 particles **per edge** unconditionally (`RM` reduced-motion is the only gate); no visible-node cap, no offscreen skip. | **5.7 REQUIRED** |
| V0.10 | Overlapping claims detected + failed? | **YES** — `extractor.py:100-112` `_ownership` builds `file → [node_ids]` and collects `doubles`; `extract()` turns each into a hard error naming file + all claimants ("claimed by multiple nodes … Invariant 4", `extractor.py:346-354`), non-zero via `ent extract` / `ent ci`. Note: claims are literal paths (no glob expansion), so realpath-glob overlap doesn't arise today. | **3.3 CLOSED** |
| V0.11 | Execution in-process, no timeout, no rlimits? | **YES (problem confirmed)** — `runner.py:165/291/413` call `entrypoint(row["input"])` directly in-process; `testing.py:9` same; no `timeout`, `subprocess`, `multiprocessing`, or `setrlimit` anywhere in the eval path. A `while True:` node hangs the suite. | **1.1 REQUIRED** |
| V0.12 | Prompt/config bytes hashed raw (no LF normalization)? | **YES (raw)** — `version.py:72` `path.read_bytes()` straight into sha256 (`_hash_bytes`, lines 49-56); no `\r\n` normalization. Cross-OS churn is real. | **5.2/5.3 REQUIRED** |
| V0.13 | Bare/`pass` except handlers in history/tracing/server/steering | **Hit list** (no bare `except:` anywhere; `except Exception` hits): `history.py:212` (`_composites_for` → `out[nid]=None`, silent), `tracing.py:84` (OTel import fallback → no-op, acceptable-by-design), `tracing.py:91` (`set_attribute` → `pass`, silent), `server.py:100` (top-level API guard → returns 500 with message, **not** silent), `extractor.py:333` (`_composite_of` defensive → None, silent — this one previously swallowed a real NameError during V1 development, proving the hazard). `steering.py`: none. | **5.6 REQUIRED** (3 silent hits to narrow/log) |

## Summary

- **Confirmed-required:** 1.1, 1.3, 1.4 (Phase 1); 2.2 (Phase 2); 3.1 (fsync/lock half), 3.2, 3.4 (Phase 3); 4.2 (Phase 4); 5.1, 5.2/5.3, 5.6, 5.7 (Phase 5).
- **Closed:** **3.3** (overlapping claims already a hard extract failure, `extractor.py:100-112,346-354`).
- Not part of the 13 but load-bearing for Phase 3: the append-only norm is already honoured (V0.3) — 3.1 needs only durability (fsync + lock + `v` field), not a dedup rewrite fix.

## Phase closure notes

### Phase 1 — honest verdicts, safe writes ✅
- **1.1 CLOSED** — `src/ent/sandbox.py`: whole-eval child process (same code path,
  so stubs/invariants/trajectory unchanged), wall-clock timeout (5s/30s,
  `evals.timeoutMs` override) → `TIER0_TIMEOUT`; POSIX rlimits (AS 512MB, CPU,
  NOFILE, NPROC) → over-alloc bounded (MemoryError). Default for `ent eval`
  (`--no-sandbox` opts out); internal read paths + explicit `entrypoint=`
  overrides stay in-process by design (closures can't cross a process boundary).
- **1.2 CLOSED** — `runner._bootstrap_verdict`: paired bootstrap over golden rows
  (10k resamples, fixed seed) with CI bounds + n + minDetectableEffect in
  stats/history; baselines store `rowScores` (write_pending/accept carry it);
  legacy baselines fall back tagged `verdictMethod: threshold-legacy`. Bonus
  honesty: a 1-row regression at n=9 is UNSTABLE (underpowered), not a false
  REGRESSED — the old threshold would have over-claimed.
- **1.3 CLOSED** — `steering.propose_from_outcome` records `baseSha256` per
  touched file; `approve` re-hashes ALL files before ANY write and refuses the
  whole apply on mismatch ("proposal stale: <file>"), proposal left open.
- **1.4 CLOSED** — `src/ent/claims.py` (`claimed_rel`/`is_within_claims`:
  realpath + `commonpath` containment + resolved-claim membership; a claim that
  is a symlink out of the repo authorises nothing). Routed:
  `mcp_server.tool_apply_edit`, `server._edit`, `editloop.check_boundary`.
- Tests: `tests/test_v6_phase1.py` (15). Suite 328 → **343**.

### Phase 2 — enforced boundary, honest health ✅
- **2.1 CLOSED** — `.claude/hooks/enforce_claims.py` (PreToolUse, matcher
  `Edit|Write|MultiEdit`, registered in `.claude/settings.json`): resolves the
  owning unit from `entiendo/graph.json` via `ent.claims` (the 1.4 authority);
  denies unclaimed files always, and other units' files while a steer is active
  (steered = claimed-but-unresolved first, else oldest pending). Fail-open by
  design: unmanaged repos (no graph.json), missing ent install, malformed
  payloads, and plane-owned paths (manifests / `entiendo/` / `evals/`) all
  allow — the hook governs unit interiors in managed trees, and must never
  brick an ordinary session. `ENT_HOOK_DISABLE=1` bypass.
- **2.2 CLOSED** — `render._tier1_latest` reads `evals.jsonl` → each unit view
  carries `tier1` (statVerdict + ciLow/ciHigh + nRows + verdictMethod);
  `universe.html` health lens draws the significance ring (REGRESSED red,
  DEGRADED amber, UNSTABLE amber-pulse; tier0 RED wins; WITHIN_BAND calm — no
  ring), dossier shows `golden: <verdict> · CI95[..] · n=..`, legend says
  "red only on statistically meaningful movement".
- **2.3 CLOSED** — `tests/test_h5_live_bridge.py`: the full Bridge loop driven
  as a client would, with edit content GENERATED from the returned node context
  (no pre-stored diff): enqueue → claim → context → apply_edit → proposal →
  visible via GET /api/proposals → approve via POST → file changed + history
  events (`proposal created/approved`).
- **2.4 delivered (code half)** — `scripts/demo_reset.sh` (one-command scratch
  rebuild, proven), runbook refreshed with the v6 guardrails (stale-proposal
  refusal, sandboxed evals, the claims hook) + reset section. **The live
  recording remains Mehar's** — STATUS keeps the residual open.
- Tests: `tests/test_v6_phase2.py` (8) + `test_h5_live_bridge.py` (1). Suite
  343 → **352**.

### Phase 3 — durability & atomicity ✅
- **3.1 CLOSED** — `history._append` holds an exclusive `fcntl.flock`
  (`msvcrt.locking` fallback; plain append if neither) for the WHOLE append:
  `seq` is computed under the lock (`_line_count`), the line is `flush()`ed +
  `os.fsync()`d before unlock, and new events carry `v: 1` (readers tolerate
  absence). Concurrent-writer test: 24 events from 6 processes → gapless unique
  seq, zero torn lines. The file is still only ever appended (V0.3's good half
  preserved).
- **3.2 CLOSED** — `ci.run_ci` gains a `tier1` stage on BLESSED goldens only
  (manifest `humanBlessed: true` AND `baselines.blessing_valid` signature
  match); unblessed/stale datasets are counted advisory and not even executed —
  they can never block. `Stage` gains `severity`/`exit_severity`;
  `CiResult.exit_code` is the MAX across stages per the Phase 7 table
  (0 pass · 1 RED/REGRESSED · 2 ERROR · 4 UNSTABLE/DEGRADED); noted in
  `.github/workflows/ci.yml`. Fixture blessing in tests is a `write_bless` test
  record in a throwaway copy — the real refundly/greenfield goldens stay
  unblessed for Mehar.
- **3.3 CLOSED** (Phase 0) — overlap already enforced at
  `extractor.py:100-112,346-354`; no change.
- **3.4 CLOSED** — `steering.claim_next` claims via
  `os.open(claimed/<rid>, O_CREAT|O_EXCL)`: the kernel arbitrates, exactly one
  concurrent consumer wins (8-process race test). `post_verdict` and
  `propose_from_outcome` are idempotent: an existing `results/<id>.json` →
  `{"duplicate": true}`, no overwrite, no second revert/proposal/history event.
  `ent serve` POSTs now require `X-Ent-Csrf` (token minted per process,
  embedded as `window.__entCsrf` + `<meta name="ent-csrf">`; enforced in
  `do_POST` via the pure `check_csrf` so `handle_api` stays pure; 403
  otherwise); bind verified `127.0.0.1` only.
- **3.5 CLOSED** — `extractor._dynamic_dep_warnings` flags
  `importlib.import_module` / `__import__` / getattr-dispatch / `subprocess` /
  `requests` / `httpx` / `urllib` in claimed .py files →
  `possibleUndeclaredDynamicDep` in graph.json, printed by `ent extract`, shown
  in the dossier (warnings, never failures). TS-extractor edges are tagged
  `verificationSource: "ts-poc"` (not `"import"`) and render declared-grade
  (dashed); documented in `docs/multi-language.md` ("absence of an edge is not
  proof of no dependency").
- Tests: `tests/test_v6_phase3.py` (16). Suite 352 → **368**.

### Phase 4 — ent dev, plugin, the brain's golden ✅
- **4.1 CLOSED** — `tests/frontend/frontend_universe.py`: 11 Playwright tests
  driving the REAL `ent serve --watch` stack in Chromium (proven green locally
  against the pinned `/opt/pw-browsers/chromium`, 7.5s): page + summary, all
  six lenses change the legend, unit dossier (click + keyboard), trace playback
  advances, timeline scrub, steer round-trip landing on the file queue
  (CSRF-protected POST end-to-end), POST-without-token → 403, seeded proposal
  approved through the dossier and applied to disk, broken manifest → auto
  reload + last-good view + drift banner, empty repo invites `ent init`. NOT
  collected by default pytest (no `test_` file prefix); optional
  `frontend` CI job gates on browser presence and never blocks.
- **4.2 CLOSED** — `server.watched_paths` (manifests + claimed files +
  `entiendo/history/*.jsonl`) polled every 500ms by a daemon watcher;
  `/api/version` is a bounded long-poll the page re-arms and
  `location.reload()`s on change; `resilient_graph` serves the LAST GOOD view
  with a `drift` flag when extract fails mid-edit (banner in the page);
  `ent dev` = `serve --watch`; the HTTP server is now ThreadingHTTPServer so
  long-polls can't starve requests (still 127.0.0.1-only + CSRF).
- **4.3 CLOSED** — `.claude-plugin/plugin.json` (MCP server `ent mcp`, the
  `entiendo-operator` skill, the `enforce_claims` PreToolUse hook) +
  `marketplace.json`; manifests validate + reference real files (tested).
  `tool_post_verdict` gains `elicit`: an MCP client that supports elicitation
  settles the approval-gated proposal in-line (approve/reject applied
  immediately); any failure — no ctx, old SDK, refusal, unrecognised answer —
  falls back to the web surface with the proposal still awaiting
  (mock-client tests for all four paths).
- **4.4 CLOSED** — `evals/refundly.decide/golden_v3.jsonl` (10 rows): 8 the
  agent gets right (phrasing/whitespace/substring-"order" variants) + 2 that
  encode IDEAL behaviour it gets wrong (unknown order refunded $0 instead of
  denied; capitalised "Order" fails to parse) → baseline 0.80, a
  discriminating benchmark. decide needs no dep stubs (self-contained local
  stand-ins), so run_tier1 executes it directly. Multi-row injected regression
  → REGRESSED via paired-bootstrap. `humanBlessed: false` and no bless record
  — **the dataset stays unblessed for Mehar**.
- Tests: `tests/test_v6_phase4.py` (13) + `tests/frontend/` (11, optional).
  Suite 368 → **381**.
