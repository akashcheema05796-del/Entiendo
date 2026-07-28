# Greenfield example

A minimal project laid out the Entiendo way (SPEC.md §1.3, §11). Five nodes —
the MVP slice (§9) — one of each shape that matters:

| Node id | Kind | What it shows |
|---|---|---|
| `retrieval.chunk_ranker` | `compute` | The full manifest: contract, invariants, tiered evals, budgets, edges |
| `retrieval.vector_store` | `compute` | A node it `calls` |
| `state.doc_index` | `state` | A store it `reads` (drawn as a cylinder) |
| `llm.gateway` | `external` | A third-party boundary with `approval.required: true` |
| `config.retrieval` | `config` | A config surface; the secret is referenced, never rendered |

Together these form a coherent little graph:

```
config.retrieval ─┐
                  ├─▶ retrieval.chunk_ranker ──calls──▶ retrieval.vector_store
llm.gateway ◀─calls┘            │                              │
                               reads                          reads
                                ▼                              ▼
                          state.doc_index ◀───────────────────┘
```

## Layout

```
greenfield/
  entiendo/            # generated artifacts (graph.json, coverage.json, ...)
  config/              # config.retrieval + its claimed retrieval.yaml
  src/
    retrieval/         # chunk_ranker: manifest, ranker.py, prompt, io schemas
    vector_store/      # vector_store: manifest + store.py
    doc_index/         # doc_index: manifest + schema.sql
    gateway/           # llm.gateway: manifest + client.py
  evals/
    retrieval.chunk_ranker/   # smoke.jsonl, golden_v2.jsonl, rubric.md
```

## Try it

From this directory:

```
ent validate      # all five manifests conform to the schema
ent extract       # emit entiendo/graph.json + coverage.json, fail on drift
ent eval retrieval.chunk_ranker   # tier0 executes the unit → GREEN/RED
ent render        # the Universe: open entiendo/render.html
ent serve         # the Universe live — steer + approve on the canvas
```

All commands are implemented (L0 → L5 + Phase 7 + the v4 Universe) — see the
repository root `README.md` and `docs/build-order.md`.
