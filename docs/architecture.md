# Architecture

From SPEC.md §3. Six strictly-separable layers, each testable alone, built in
order. This file maps each layer to where it lives in the tree.

```
L0  Manifest & schema layer   — declaration + validation
L1  Extractor / reconciler    — emits graph.json + coverage.json; fails on drift
L2  Instrumentation           — OTel spans tagged with node_id; eval runner; cost meter
L3  History store             — append-only versions + eval results + traces
L4  Render surface            — one topology, six lenses
L5  Scoped edit loop          — node → AI context → edit → eval → verdict
```

| Layer | In this repo | Notes |
|---|---|---|
| L0 | `schemas/node.schema.json`, `src/ent/manifest.py`, `commands/{init,validate}.py` | The manifest is the contract for the whole system. |
| L1 | `src/ent/extractor.py`, `src/ent/version.py`, `commands/extract.py` | Reconciles declared vs actual deps. Divergence fails the build (Invariant 5). |
| L2 | `src/ent/instrument.py`, `src/ent/evals/`, `commands/eval.py` | `@ent.node()` is the single piece of code that must live in the app. |
| L3 | `src/ent/history.py`, `version.py`, `commands/snapshot.py` | Append-only JSONL event log; composite versions. Storage split target: git + Parquet/DuckDB + span store. |
| L4 | `src/ent/render.py`, `commands/render.py` | Lenses 1/4/5 shipped (structure, health, timeline); 2/3/6 next. Read-only, never in the request path (Invariant 2). |
| L5 | Phase 6 | Context assembler + claim-boundary enforcement + approval gates. |

## Trace binding (L2)

A decorator/middleware `@ent.node("retrieval.chunk_ranker")` emits an
OpenTelemetry span with `entiendo.node_id` as an attribute. Without this, the
flow and trace lenses cannot exist. It is the single piece of code that must be
in the app. In this scaffold it is a transparent pass-through — importing it and
decorating is safe and changes nothing until Phase 3.

## Storage split (L3)

- Node versions & manifests → git (content-addressed, free history)
- Eval results & budgets → time-series (DuckDB/Parquet is enough to start)
- Traces → span store (OTel-compatible), sampled
- Graph snapshots → `graph.json` per commit

Prefer boring, inspectable storage (Parquet/DuckDB, JSON, git) over a database
service — the tool must be trivially recoverable (SPEC.md §12).

## The six lenses (L4)

One topology, six views — same boxes every time, only the meaning of colour and
motion changes (SPEC.md §4): **Structure**, **Flow**, **Trace**, **Health**,
**Timeline**, **Blast radius**. All six ship (Phases 4–5): structure/health/
timeline first, then flow/trace/blast. Every lens must terminate in an action —
edit, revert, or approve — or it gets cut (SPEC.md §10); the scoped edit loop
(L5, Phase 6) provides that action surface.
