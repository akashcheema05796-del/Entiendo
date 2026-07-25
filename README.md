# Entiendo

[![CI](https://github.com/akashdatageek/Entiendo/actions/workflows/ci.yml/badge.svg)](https://github.com/akashdatageek/Entiendo/actions/workflows/ci.yml)

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

## Status: L0 → L5 + Phase 7 (real evals) implemented

All six phases (SPEC.md §8) plus **Phase 7 (real evals)** are implemented. The
full loop works end to end: declare nodes → reconcile the graph → instrument →
**execute + eval** → record history → render six lenses → edit through the node.

```
$ ent validate            # schema + semantic checks (incl. restricted invariants)
$ ent init                # scaffolds entiendo/ (+ a starter manifest)
$ ent extract             # graph.json + coverage.json; fails on drift; proposes entrypoints
$ ent eval <node>         # tier0 EXECUTES the node → GREEN/RED/UNTESTED/ERROR
$ ent eval --all --tier 1 # golden: minRuns + significance + budgets (the pre-merge gate)
$ ent bless <node>        # sign a golden dataset's content (humanBlessed, void on change)
$ ent baseline accept <n> # promote a pending baseline
$ ent snapshot            # record composite versions + verdicts to append-only history
$ ent render              # self-contained HTML map: six lenses + "executable N/M"
$ ent edit <node>         # scoped edit loop: context + boundary + verdict + approval
$ ent retrofit <root>     # infer nodes in an unmanaged repo → staged manifest proposals
$ ent serve               # interactive web app: click a node, ask an AI to change it, watch tier0
```

> **The one-line test (Phase 7 §15):** break `ranker.py` and run
> `ent eval retrieval.chunk_ranker`. It goes **RED** and names the failed
> invariant with the real numbers (`len(output.chunks)=2 <= input.k=1`). That is
> the difference between an instrument and a diagram — see [`docs/phase7.md`](./docs/phase7.md).

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
- **`ent eval` + `@ent.node()`** — L2 instrumentation + **Phase 7 real evals**:
  the decorator emits an OTel-compatible span carrying `entiendo.node_id` (and
  `ent.record()` meters cost/tokens), never in the request path (Invariant 2).
  **tier0 now executes the node** over fixture rows in isolation (dependency calls
  served from stubs; any unstubbed call is a `TIER0_IO_VIOLATION`) and evaluates
  the real invariants against real output via a restricted AST evaluator (no
  `eval`/`exec`) → GREEN/RED/UNTESTED/ERROR. **tier1** replays `minRuns` times,
  scores with the metric, and applies anti-flicker statistics
  (WITHIN_BAND/REGRESSED/IMPROVED/UNSTABLE) + budgets (DEGRADED); `humanBlessed`
  is enforced by a content signature. See `src/ent/evals/`, `src/ent/invariants.py`,
  `src/ent/testing.py`, `docs/phase7.md`.
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
- **`ent retrofit`** — the §12 v2 path: infers node boundaries in an *unmanaged*
  repo (directory grouping, kind from extensions, deps from static imports,
  entrypoint from a lone public function) and stages one manifest proposal per
  node for node-by-node review (`--accept`). Semi-automated migration, never a
  silent scan. `examples/legacy/` is the demo input. See `src/ent/retrofit.py`.
- **`ent serve`** — the interactive edit surface: a localhost web app (stdlib
  backend, self-contained frontend) where you click a node, see its scoped
  context, run tier0/tier1, and describe a change in natural language. An LLM
  (Claude Opus 5, via the `anthropic` SDK) edits **only within the node's
  claims**, tier0 reruns, and the verdict + blast radius + approval gate surface
  live — with a one-click revert. The map stays read-only (Invariant 2); only the
  edit endpoint writes. The model is optional (`pip install -e '.[serve]'` + an
  API key); without it the explorer and evals still work. See `src/ent/server.py`,
  `src/ent/agent.py`, `docs/edit-surface.md`.
- **[`examples/greenfield/`](./examples/greenfield/)** — a five-node example
  project laid out the Entiendo way. Full loop:
  `cd examples/greenfield && ent validate && ent extract && ent snapshot && ent render && ent edit retrieval.chunk_ranker`.
- **`src/ent/`** — the package: CLI, one module per layer.

---

## What a project looks like

Point Entiendo at a repo and every declared component becomes a **node** on one
topology you steer through — not a folder in a tree. This is
[`examples/greenfield/`](./examples/greenfield/): five nodes, reconciled at 100%
coverage. Run `cd examples/greenfield && ent extract` and this is the graph it
derives:

```mermaid
flowchart LR
  subgraph retrieval[" retrieval "]
    ranker["retrieval.chunk_ranker<br/><small>compute · 🟢 GREEN</small>"]
    vstore["retrieval.vector_store<br/><small>compute · 🟢 GREEN</small>"]
    idx["state.doc_index<br/><small>state · ⚪ untested</small>"]
    cfg["config.retrieval<br/><small>config · ⚪ untested</small>"]
  end
  subgraph llm[" llm "]
    gw["llm.gateway<br/><small>external · ⚪ untested</small>"]
  end

  ranker -->|calls ✓| vstore
  ranker -->|calls ✓| gw
  ranker -.->|reads| idx
  ranker -.->|config| cfg
  vstore -.->|reads| idx
  vstore -.->|config| cfg
  gw    -.->|config| cfg

  classDef compute fill:#3b82f6,stroke:#1c1c22,color:#fff;
  classDef state fill:#8b5cf6,stroke:#1c1c22,color:#fff;
  classDef config fill:#64748b,stroke:#1c1c22,color:#fff;
  classDef external fill:#f59e0b,stroke:#1c1c22,color:#111;
  class ranker,vstore compute;
  class idx state;
  class cfg config;
  class gw external;
```

**Reading the map:** colour is the node **kind** (blue `compute` · violet `state`
· slate `config` · amber `external`). A **solid** arrow is an edge the extractor
*verified* against a real import (`✓`); a **dashed** arrow is declared but not
statically provable (`reads`/`config`). Health is the node's tier0 verdict —
🟢 GREEN means the node **executed** and its invariants held, ⚪ means no
executable eval yet. An undeclared import would fail `ent extract` naming both
nodes (Invariant 5), so what you see is guaranteed to match the code.

### The rendered surface — `ent render`

`ent render` builds a **self-contained HTML page** (inline CSS/JS, no build step,
read-only) with one topology and six lenses — a browser tab each:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Entiendo — Structure                                                      │
│  5 nodes · 7 edges · coverage 100% · executable 2/5 · reconciled ✓  @a1b2c │
├──────────────────────────────────────────────────────────────────────────┤
│ │1·Structure│ 2·Flow │ 3·Trace │ 4·Health │ 5·Timeline │ 6·Blast radius │ │
├──────────────────────────────────────────────────────────────────────────┤
│  retrieval                                                                 │
│  ▎retrieval.chunk_ranker        [compute] [mehar]        v: a1b2c3d        │
│  ▎  calls retrieval.vector_store ✓ · calls llm.gateway ✓ · reads … · config…│
│  ▎retrieval.vector_store        [compute] [mehar]        v: c3d4e5f        │
│  ▎  reads state.doc_index · config config.retrieval                        │
│  llm                                                                       │
│  ▎llm.gateway                   [external] [mehar]       v: 9f8e7d6        │
└──────────────────────────────────────────────────────────────────────────┘
```

The **Health** lens re-colours the same cards by tier0 verdict (it calls the same
`run_tier0` as `ent eval`, so the colour matches by construction):

```
  🟢 retrieval.chunk_ranker   GREEN      executed · invariants held
  🟢 retrieval.vector_store   GREEN      executed · invariants held
  ⚪ config.retrieval         UNTESTED   no executable eval
  ⚪ llm.gateway              UNTESTED   no executable eval
  ⚪ state.doc_index          UNTESTED   no executable eval
```

The other four: **Flow** (edge direction + per-node traffic volume), **Trace**
(per-hop latency/cost of one recorded request), **Timeline** (version + eval
history), **Blast radius** (click a node → its transitive downstream dependents
light up, ranked by coupling).

### The interactive edit loop — `ent serve`

`ent serve` puts that surface behind a localhost web app: click a node → its
scoped context; describe a change in English → an LLM edits it **within the
node's claims**, tier0 reruns, and the verdict + blast radius + approval gate
update live, with one-click revert:

```
┌ nodes (by health) ┬ retrieval.chunk_ranker ──────────────────────────────┐
│ 🟢 chunk_ranker    │ claims:   src/retrieval/ranker.py                     │
│ 🟢 vector_store    │ contract: len(output.chunks) <= input.k              │
│ ⚪ doc_index       │ neighbours (contracts only): vector_store · gateway   │
│ ⚪ gateway         │ [ Run tier0 ]  [ Run tier1 ]                          │
│ ⚪ retrieval.cfg   │ ┌ describe a change ─────────────────────────────┐    │
│                   │ │ clamp scores into [0, 1]                        │    │
│                   │ └──────────────────────────── [ propose & apply ]┘    │
│                   │ verdict:  🟢 GREEN · ready-to-merge                    │
│                   │ blast radius:  0 downstream        [ diff ] [ revert ] │
└───────────────────┴───────────────────────────────────────────────────────┘
```

The map stays read-only (Invariant 2); only the edit endpoint writes, and only
inside the claims. A red edit is **blocked**, and the pre-edit content is backed
up for revert.

---

## How you work with it

Two ways in, same guarantees. Either you drive the loop from the **CLI**, or an
**AI edits through the node** (`ent serve`, or `ent mcp` with Claude Code).

### The loop

```mermaid
flowchart LR
  D["declare<br/><small>entiendo.node.yaml</small>"] --> V["ent validate<br/><small>L0 schema + rules</small>"]
  V --> X["ent extract<br/><small>graph.json + coverage.json<br/>fail on drift</small>"]
  X --> E["ent eval<br/><small>tier0 executes the node<br/>GREEN / RED</small>"]
  E --> R["ent render<br/><small>six lenses</small>"]
  R --> C["change it<br/><small>ent edit · serve · mcp</small>"]
  C -->|"confined to claims<br/>tier0 reruns"| E
```

The manifest **is** the retrieval index: an edit loads only the node's claimed
file bodies + its immediate neighbours' contracts (no bodies) — never the whole
repo (Invariant 8). Every edit is boundary-checked, re-evaluated, and gated
(`ready-to-merge` / `awaiting-signoff` / `blocked`) before it counts as done.

### Editing through the node with Claude Code (`ent mcp`)

Register Entiendo as an MCP server (`.mcp.json` → `{ "command": "ent", "args":
["mcp"] }`) and Claude Code reads and writes *through the node*, not the file
tree:

```mermaid
sequenceDiagram
  participant CC as Claude Code
  participant E as Entiendo · ent mcp
  CC->>E: get_node_context(node)
  E-->>CC: manifest + claimed file bodies<br/>+ neighbour contracts only
  CC->>E: apply_edit(node, files)
  Note over E: rejects paths outside claims<br/>backs up · reruns tier0
  E-->>CC: verdict · blast radius · approval
  Note over CC: red → revert_node(node)
```

A quick tour, end to end:

```bash
pip install -e '.[dev,mcp]'
cd examples/greenfield
ent validate                        # L0: manifests conform
ent extract                         # L1: graph.json + coverage.json (no drift)
ent eval retrieval.chunk_ranker     # L2/Phase 7: executes → 🟢 GREEN
ent render && open entiendo/render.html  # L4: the six-lens map above
ent serve                           # L5: click-and-edit surface (needs [serve])
ent mcp                             # L5: same surface as MCP tools for Claude Code
```

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
