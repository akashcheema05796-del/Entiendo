# Phase 7 — Real Evals

> Today `GREEN` used to mean "the YAML is well-formed." Phase 7 makes it mean
> "the node behaved." A node's eval now *executes the node*.

## The execution contract (§1)

A node is run through its entrypoint:

```yaml
contract:
  entrypoint: src/retrieval/ranker.py::rank   # <module path>::<callable>
```

- `entrypoint` is **optional**. A node without one is `UNTESTED`, not a build
  failure — this avoids fake entrypoints written just to go green.
- The module path **must be in `claims`** (validation error otherwise).
- The callable takes one dict (the input) and returns one dict (the output).
- Cross-checked against `@ent.node()`: if the resolved callable is decorated for
  a *different* node id, that is **drift** (`ent extract` reports it; `ent eval`
  errors). A decorated node with no entrypoint gets a **proposed** line in
  `graph.json` `proposedEntrypoints`.

## Isolation (§2)

**During tier0 a node may not perform I/O.** I/O is modelled as calls through
`@ent.node()` neighbours, so each fixture row supplies canned responses:

```jsonl
{"name": "ranks_within_k", "input": {...}, "deps": {"llm.gateway": [{...}]}}
```

- Unstubbed dependency called → `TIER0_IO_VIOLATION` (naming the node) → `ERROR`.
- More calls than stubs → queue exhausted → `ERROR`.
- Pure nodes (no `dependencies.calls`) skip the stub layer and just run.
- `evals.executionMode: skip` downgrades a node to `UNTESTED` — explicit, counted.

## Invariants (§4)

Invariants are Python expressions over exactly `input` and `output`, evaluated
against the **real** output. There is **no `eval()`/`exec()`** — a restricted
allowlist AST is validated at `ent validate` time and interpreted by a
tree-walker. Attribute access on dicts is key access (`output.chunks` →
`output["chunks"]`). Failures print the real values:
`len(output.chunks)=12 <= input.k=5`.

**Agentic units — the `trajectory` reflex.** For a unit with an `interior`, a
`trajectory` tier0 eval checks the recorded *sequence* of tool calls rather than
the answer: the `order` rules (`order_lookup before issue_refund`), the `maxSteps`
ceiling, and `registryOnly` (no call to a tool outside the declared registry). A
RED verdict names the violated rule, and the Universe renders the same result —
the orbit ring dashes when `registryOnly` is off, and trace playback lights each
tool as the agent calls it, so an out-of-order call is visible even when the
final output is correct. `refundly.decide` is the worked example.

## Verdicts (§5)

| Verdict | Meaning | Health |
|---|---|---|
| `GREEN` | executed, all checks passed | green |
| `RED` | executed, a check failed | red |
| `UNTESTED` | no entrypoint / executionMode: skip | grey |
| `ERROR` | harness failure (import, I/O violation) | amber |

The render surface shows two denominators: `coverage 100% · executable 2/5`.

## tier1 — golden runner (§6, §7, §9)

`ent eval <node> --tier 1` runs the node `minRuns` times over a golden dataset
(real I/O permitted), scores with the `metric`, and judges the distribution:

- `|delta| <= significance` → **WITHIN_BAND** (green)
- `delta < -significance` and `|delta| > spread` → **REGRESSED** (red)
- `delta > significance` and `|delta| > spread` → **IMPROVED** (green; writes a
  baseline *proposal*, never auto-promoted)
- `|delta| > significance` but `<= spread` → **UNSTABLE** (amber; too noisy)

Budgets (`p95LatencyMs`, `costPerCallUsd`) over budget → **DEGRADED**. Every run
is appended to `entiendo/history/evals.jsonl` with the `compositeVersion`.

`n=` is printed with every verdict — with `minRuns: 5` this is a guardrail, not a
p-value.

## Blessing (§8)

`humanBlessed` has teeth: `ent bless <node>` signs the dataset **content**
(sha256) into `entiendo/baselines/<node>.bless.json`. At tier1 time the runner
rehashes; if the dataset changed since blessing, the blessing is void and the run
is **advisory-only** (never gates). Blessing content, not a filename, is what
stops an AI from editing its own golden rows into a pass.

## CLI

```
ent eval <node>              tier0 (executes the node)
ent eval <node> --tier 1     golden
ent eval --all [--tier 1]    every node (the health sweep / pre-merge gate)
ent bless <node>             sign a golden dataset
ent baseline accept <node>   promote a pending baseline
```

Exit codes: `0` pass/within-band · `1` RED/REGRESSED · `2` ERROR · `4`
UNSTABLE/DEGRADED. Advisory tier1 runs never block (0).
