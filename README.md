# Entiendo

> *entiendo* — Spanish for "I understand." The whole claim of the tool is that
> the human **and** the model can say "I understand this system." CLI binary: `ent`.

**When AI writes the code, the file tree stops being the right interface.** The
unit of work becomes the **node** — a declared component with a contract, a
version, an eval, and a history. Entiendo makes that node the surface a human
steers through *and* the retrieval unit an AI edits through.

> Instrumentation at **build time**, not forensics after breakage. Sensors go in
> while you build, so "which part broke" is already answered when something turns red.

The full specification is **[SPEC.md](./SPEC.md)** — it is the source of truth.
This README is the map to the scaffold.

---

## Status: complete — L0 → L5 implemented

All six phases (SPEC.md §8) are **implemented**. The full loop works end to end:
declare nodes → reconcile the graph → instrument + eval → record history →
render six lenses → edit through the node.

```
$ ent validate       # validates every entiendo.node.yaml; specific errors; exit 0/1
$ ent init           # scaffolds entiendo/ (+ a starter manifest with --node-id/--at)
$ ent extract        # emits graph.json + coverage.json; fails on undeclared-dep drift
$ ent eval <node>    # runs tier0 (schema/invariant/smoke); green/red verdict, <2s
$ ent snapshot       # records composite versions + verdicts to append-only history
$ ent render         # builds a self-contained HTML map: all six lenses
$ ent edit <node>    # scoped context; --changed reviews an edit (boundary+verdict+approval)
```

What **is** real today:

- **[`SPEC.md`](./SPEC.md)** — the complete specification (v2).
- **[`schemas/node.schema.json`](./schemas/node.schema.json)** — the manifest
  JSON-Schema. This is *the contract for the entire system* (SPEC.md §12).
- **`ent validate` / `ent init`** — L0 boundaries: schema conformance plus the
  semantic rules (id uniqueness, `$ref` resolution, claim existence, the
  `humanBlessed` gate on tier1 golden sets). See `src/ent/validation.py`.
- **`ent extract`** — L1 reconciler: AST import analysis derives actual edges and
  checks them against declared `dependencies`. Undeclared edges are drift and
  fail the build (Invariant 5); it emits `graph.json` + `coverage.json`. See
  `src/ent/extractor.py`.
- **`ent eval` + `@ent.node()`** — L2 instrumentation: the decorator emits an
  OTel-compatible span carrying `entiendo.node_id` (and `ent.record()` meters
  cost/tokens), never in the request path (Invariant 2). `ent eval` runs the
  deterministic tier0 checks (schema / invariant / smoke) to a green/red verdict.
  See `src/ent/instrument.py`, `src/ent/tracing.py`, `src/ent/evals/runner.py`.
- **`ent snapshot` + `ent render`** — L3/L4: `snapshot` records composite
  versions (code/prompt/config/model) + tier0 verdicts to an append-only history
  log (version events dedup, so the timeline shows *changes*); `render` builds a
  self-contained HTML system map with **all six lenses** — structure (kind/group),
  flow (edge direction + trace volume), trace (per-hop latency/cost of a recorded
  request), health (verdict colour, matches `ent eval`), timeline (version + eval
  history), and blast radius (downstream dependents ranked by coupling).
  Record a request with `history.capture_trace(root, trace_id=...)`. Read-only,
  never in the request path (Invariant 2). See `src/ent/render.py`,
  `src/ent/history.py`, `src/ent/version.py`.
- **`ent edit`** — L5 scoped edit loop: assembles a context of only the node's
  claimed file bodies + immediate neighbours' contracts (no bodies) + recent
  evals + baseline — the AI edits through the node, not the repo (Invariant 8).
  `--changed` enforces the claim boundary, reruns tier0, shows blast radius, and
  applies the approval gate. See `src/ent/editloop.py`.
- **[`examples/greenfield/`](./examples/greenfield/)** — a five-node example
  project laid out the Entiendo way. Full loop:
  `cd examples/greenfield && ent validate && ent extract && ent snapshot && ent render && ent edit retrieval.chunk_ranker`.
- **`src/ent/`** — the package: CLI, one module per layer.

---

## The node

Everything hangs off one schema. A node is declared by an `entiendo.node.yaml`
colocated with the code it owns:

```yaml
apiVersion: entiendo/v1
kind: Node
id: retrieval.chunk_ranker      # stable, globally unique
nodeKind: compute               # compute | state | schema | config | external | pipeline
owner: mehar                    # human accountable, not the AI
claims: [src/retrieval/ranker.py, src/retrieval/prompts/rank_v3.md]
contract:
  invariants: ["len(output.chunks) <= input.k"]
  sideEffects: none
dependencies: { calls: [retrieval.vector_store, llm.gateway], reads: [state.doc_index] }
evals:
  tier0: [{ type: schema_validation }, { type: invariant_check }]
```

See the fully-annotated version in
[`examples/greenfield/src/retrieval/entiendo.node.yaml`](./examples/greenfield/src/retrieval/entiendo.node.yaml)
and the field-by-field reference in [`docs/manifest.md`](./docs/manifest.md).

---

## CLI

| Command | Layer | Does |
|---|---|---|
| `ent init` | L0 | scaffold `entiendo/` + a first node manifest |
| `ent validate` | L0 | validate manifests against the schema |
| `ent extract` | L1 | emit `graph.json` + `coverage.json`; fail on drift |
| `ent eval <node>` | L2 | run a node's evals (tier0 by default) |
| `ent render` | L4 | serve the render surface (six lenses) |

All are wired; L0 onward is filled in over the build order below.

---

## Architecture (L0 → L5)

Strictly separable layers, each testable alone, built in order
(SPEC.md §3, §8). See [`docs/architecture.md`](./docs/architecture.md) and
[`docs/build-order.md`](./docs/build-order.md).

```
L0  Manifest & schema      declaration + validation          src/ent/manifest.py, schemas/
L1  Extractor / reconciler graph.json + coverage.json         src/ent/extractor.py, version.py
L2  Instrumentation        @ent.node() spans; eval runner     src/ent/instrument.py, evals/
L3  History store          append-only versions + evals       src/ent/history.py
L4  Render surface         one topology, six lenses           (Phase 4/5)
L5  Scoped edit loop        node → context → edit → verdict   (Phase 6)
```

---

## Repo layout

```
Entiendo/
  SPEC.md                     the specification (source of truth)
  README.md                   this file
  pyproject.toml              package + `ent` console script
  schemas/
    node.schema.json          manifest contract (JSON-Schema)
  src/ent/                    the tool
    cli.py                    argparse entry; one file per subcommand under commands/
    commands/                 init, validate, extract, eval, render
    manifest.py               L0  node model: discover, load, Node
    schema.py                 L0  schema load + validator
    validation.py             L0  schema + semantic checks
    extractor.py              L1  reconciler (stub)
    version.py                L1/L3 composite versioning (stub)
    instrument.py             L2  @ent.node() decorator (safe pass-through)
    evals/                    L2  tiered eval runner (stub)
    history.py                L3  append-only store (stub)
  examples/greenfield/        a five-node example project
  docs/                       architecture, build order, manifest reference
  tests/                      scaffold-coherence checks
```

---

## Develop

```bash
pip install -e ".[dev]"     # editable install; provides the `ent` command
ent --version
pytest                       # scaffold-coherence tests (schema loads; examples conform)
```

Guiding invariants (SPEC.md §2): the map is generated never drawn; Entiendo is a
read-only observer, never in the request path; no node without a contract, no
contract without a tier-0 eval; every file is claimed exactly once or explicitly
unclaimed; manifests are verified, not trusted; secrets are never rendered.
