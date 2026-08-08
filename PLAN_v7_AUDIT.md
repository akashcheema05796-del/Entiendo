# PLAN_v7 — Phase 0 Audit

Recorded against `main @ 9d3aaa4` (post-#56). Suite: **400 tests collected**
(the plan's "389/389" predates PRs #52–#56; the floor is now 400 + 12 optional
Playwright browser tests).

## Symbol table

| Symbol | What it is | Path | Notes |
|---|---|---|---|
| `<RENDER_MODULE>` | `ent render` implementation | `src/ent/render.py` (CLI: `src/ent/commands/render.py`) | `build_view()` at render.py:24 assembles the model; `render_html()` at :279 embeds it |
| `<HTML_TEMPLATE>` | universe markup/JS | `src/ent/universe.html` — **a real standalone file**, loaded at render.py:349 (`_UNIVERSE = (Path(__file__).parent / "universe.html").read_text()`) | NOT an inline f-string — the plan's "extract it first" contingency does not apply |
| `<RENDER_PAYLOAD>` | object serialized into the page | the `view` dict from `build_view()` (render.py:24) | plain dict; per-node views built in the loop at render.py:44–80; embedded via `<script id="view" type="application/json">` |
| `<DEV_SERVER>` | `ent dev` implementation | `src/ent/server.py` (`serve(watch=True)`); CLI alias in `src/ent/commands/serve.py` | ThreadingHTTPServer, 127.0.0.1 only |
| `<DEV_ROUTES>` | route table | server.py `handle_api` (:35) + Handler | `GET /api/graph`, `GET /api/version` (long-poll, Handler-level), `POST /api/steer`, `GET /api/steering`, `GET /api/proposals`, `POST /api/proposals/<id>/approve\|reject`, `GET/POST /api/node/<id>/(context\|eval\|edit\|revert\|replay)` |
| `<CSRF_GUARD>` | v6 CSRF | server.py `check_csrf`/`inject_csrf`; token minted per process in `serve()`, embedded as `window.__entCsrf` + `<meta name="ent-csrf">`; enforced in `do_POST` (403), `handle_api` stays pure |
| `<HISTORY_READER>` | events.jsonl reader | `src/ent/history.py` — `read_events`, `timeline`, `latest_version`; append via locked `_append` |
| `<EVAL_VERDICT>` | tier1 statistics | `src/ent/evals/runner.py` `_bootstrap_verdict(new_rows, base_rows, sig)` → `(verdict, detail, boot)` where boot = `{verdictMethod, ciLow, ciHigh, nRows, minDetectableEffect}`; run stats add `runs, mean, spread, baseline, n, metric, rowScores, delta, blessed` | note: **no `pValue` field exists** — the engine is CI-bounds-based; Phase 1 maps the plan's `pValue/significant` to `ciLow/ciHigh/statVerdict` honestly rather than inventing a p-value |
| `<CLAIMS>` | ownership resolution | `src/ent/claims.py` — `expand_claims` (globs, v7), `resolved_claims`, `claimed_rel` |
| `<RENDER_TESTS>` | render coverage | `tests/test_universe.py` (DOM-structure over emitted HTML), `tests/test_render*.py`, browser: `tests/frontend/frontend_universe.py` (12 Playwright tests, **Playwright IS already a dev dependency in this environment** — Phase 2 may use it) |

## Questions

**A1 — static or fetching?** Both, decided at render.py:289 `build_universe(view)`:
static `ent render` embeds the JSON; `ent serve/dev` passes `None` →
`<script id="view">null</script>` and the page fetches `/api/graph`
(universe.html: `const STATIC = EMBEDDED !== null; view = STATIC ? EMBEDDED :
(await api('GET','/api/graph')).data`).

**A2 — per-node payload today?** From build_view: `id, name, nodeKind, group,
owner, status, claims (patterns), claimedFileCount, sideEffects, spanName,
approvalRequired, health, healthColour, version{code,prompt,config,model,composite},
description, task, invariants, budgets{...,measured{p95Basis,...}},
trajectoryVerdict, blessing, tier1{statVerdict,ciLow,ciHigh,nRows,mean,baseline,
verdictMethod,blessed,ts}, blindSpots, interior?` — plus top-level `edges,
timelines, traces, traffic, dependencyCycles, coverage`. Phase 1 adds:
`payloadVersion: 2`, per-node `evals.tier0` rollup, `history` (last 20),
`neighbours{out,in}` with `verified`.

**A3 — DOM overlay?** Yes, already: fixed DOM panels over the canvas
(`#dossier`, `#lenses`, `#legend`, `#timebar`, `#search`, `#drift-banner`).
The canvas is z-index 1; chrome sits above. Phase 2's window layer joins an
existing overlay stack — z-index 20+ is free.

**A4 — watcher signal?** Full reload: `_Watcher` polls mtimes (500ms), bumps
`version`; the page long-polls `GET /api/version?since=` (bounded 25s,
Handler-level) and calls `location.reload()` on change. Failed extract mid-edit
→ `resilient_graph` serves last good view + drift banner.

**A5 — secret stripping?** `version._strip_secrets` (v6 5.1): config lines
whose key matches the secret regex contribute the KEY, never the VALUE, to the
config hash. **Config file *contents* are never embedded in the payload at
all** — only hashes and manifest fields. Phase 1 must keep it that way: the
manifest tab renders manifest fields, never raw config file bodies.

## Deviations Phase 1+ will make from the plan text (declared now)

1. `pValue` → the engine is paired-bootstrap CI, not NHST; the payload carries
   `ciLow/ciHigh/statVerdict/significant` (significant = CI excludes 0). No
   invented p-values.
2. Workspace file lives at `entiendo/workspace.json` (the existing artifact
   tree), not `.entiendo/` — one storage convention, not two. Git-ignored.
3. Playwright exists → Phase 2 adds DOM behaviour tests to the optional
   browser suite as well as the structural pytest assertions.
4. Suite floor is 400, not 389.
