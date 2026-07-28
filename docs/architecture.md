# Architecture

From SPEC.md §3. Six strictly-separable layers, each testable alone, built in
order. This file maps each layer to where it lives in the tree.

```
L0  Manifest & schema layer   — declaration + validation
L1  Extractor / reconciler    — emits graph.json + coverage.json; fails on drift
L2  Instrumentation           — OTel spans tagged with node_id; eval runner; cost meter
L3  History store             — append-only versions + eval results + traces
L4  The Universe              — one navigable canvas, six real lenses
L5  Steer + approve           — unit → AI context → edit → eval → verdict → approval
```

| Layer | In this repo | Notes |
|---|---|---|
| L0 | `schemas/node.schema.json`, `src/ent/manifest.py`, `commands/{init,validate}.py` | The manifest is the contract for the whole system. |
| L1 | `src/ent/extractor.py`, `src/ent/version.py`, `commands/extract.py` | Reconciles declared vs actual deps. Divergence fails the build (Invariant 5). |
| L2 | `src/ent/instrument.py`, `src/ent/evals/`, `commands/eval.py` | `@ent.node()` is the single piece of code that must live in the app. |
| L3 | `src/ent/history.py`, `version.py`, `commands/snapshot.py` | Append-only JSONL event log; composite versions. Storage split target: git + Parquet/DuckDB + span store. |
| L4 | `src/ent/render.py`, `src/ent/universe.html`, `src/ent/replay.py`, `commands/{render,serve,pin,replay}.py` | The **Universe**: one navigable canvas, all six lenses real (trace playback, timeline scrubber, cost overlay, rendered agentic interiors). Read-only, never in the request path (Invariant 2). |
| L5 | `src/ent/editloop.py`, `src/ent/server.py`, `src/ent/steering.py`, `src/ent/{agent,mcp_server}.py`, `commands/{edit,serve,mcp}.py` | Context assembler + claim-boundary enforcement + tier0 rerun + blast radius + approval gates. `ent serve` steers on the canvas; the **Bridge** (steer queue → operator → verdict) drives Claude Code as the workload; approval-gated edits land as diff-first **proposals**. |

## Trace binding (L2)

A decorator/middleware `@ent.node("retrieval.chunk_ranker")` emits an
OpenTelemetry span with `entiendo.node_id` as an attribute. Without this, the
flow and trace lenses cannot exist. It is the single piece of code that must be
in the app — a transparent pass-through that never changes behaviour (Invariant
2), now implemented: it times the call, binds `entiendo.node_id`, meters
cost/tokens via `ent.record()`, and `ent.guard(registry)` gates an agentic unit's
tool calls to its declared registry.

## Storage split (L3)

- Node versions & manifests → git (content-addressed, free history)
- Eval results & budgets → time-series (DuckDB/Parquet is enough to start)
- Traces → span store (OTel-compatible), sampled
- Graph snapshots → `graph.json` per commit

Prefer boring, inspectable storage (Parquet/DuckDB, JSON, git) over a database
service — the tool must be trivially recoverable (SPEC.md §12).

## The six lenses (L4) — the Universe

One **navigable canvas** (`universe.html`, celestial design system, world camera,
search, minimap, group collapse), not six pages — the lens switches what the same
topology *shows* (SPEC.md §4): **Structure**, **Flow**, **Trace**, **Health**,
**Timeline**, **Blast radius**. All six are real (Phases 4–5 + the v4 layer):

- **Trace** plays a recorded request back as a comet walking its hops; a failed
  hop halts it red, and over an agentic unit it **descends into the interior**,
  lighting each tool as the agent calls it.
- **Timeline** is a scrubber over the real commit axis — drag it and a unit's
  fingerprint replays against that past commit (`replay.py`).
- **Health** recolours by the same `run_tier0` verdict as `ent eval`.
- Agentic units render their `interior` as tool **satellites on an orbit ring**,
  tethered across the border to the unit each tool crosses.

Every lens terminates in an action — steer, revert, or approve — or it gets cut
(SPEC.md §10); the L5 surface (`ent serve`, the Bridge) provides it, including
diff-first approval for gated units.
