# Build order

From SPEC.md §8. Each phase ships something testable. **Do not start a phase
before the previous one's acceptance criteria pass.** This file tracks status.

Legend: ☐ not started · ◐ in progress · ☑ done

| Phase | Layer | Status |
|---|---|---|
| 1 | L0 — Boundaries | ◐ scaffold only |
| 2 | L1 — Extractor & reconciler | ☐ |
| 3 | L2 — Instrumentation + eval runner | ☐ |
| 4 | L3/L4 — History + render (lenses 1, 4, 5) | ☐ |
| 5 | L4 — remainder (lenses 2, 3, 6) | ☐ |
| 6 | L5 — Scoped edit loop | ☐ |

---

## Phase 1 — L0: Boundaries
Manifest schema, JSON-Schema validator, `ent init`, `ent validate`.

**Acceptance:** a repo with 3 hand-written manifests validates; a malformed one
fails with a useful error.

Scaffold present: `schemas/node.schema.json`, `src/ent/manifest.py`,
`src/ent/commands/{init,validate}.py`, `examples/greenfield/` (5 manifests).
Remaining: the parser/model in `manifest.py` and the real validate/init logic.

## Phase 2 — L1: Extractor & reconciler
Static analysis of claimed files → actual imports/calls. Emit `graph.json`,
`coverage.json`. Fail on declared-vs-actual divergence.

**Acceptance:** deliberately add an undeclared dependency → build fails naming
both nodes. Coverage number is correct.

## Phase 3 — L2: Instrumentation + eval runner
`@ent.node()` decorator, OTel span attribution, tier0 runner, cost meter.

**Acceptance:** one real request produces spans mapped to node IDs;
`ent eval <node>` returns tier0 verdict in <2s.

## Phase 4 — L3/L4: History + render (lenses 1, 4, 5)
Append-only history store. Web surface: structure, health, timeline. Ship these
three first — they deliver the "everything under control" glance.

**Acceptance:** a node's version change is visible on the timeline within one
commit; health colour matches `ent eval` output.

## Phase 5 — L4 remainder: lenses 2, 3, 6
Flow, trace, blast radius.

## Phase 6 — L5: Scoped edit loop
Context assembler, claim-boundary enforcement, auto tier0 rerun, approval gates.

**Acceptance:** clicking a node and requesting a change produces an edit confined
to `claims`, with a pass/fail verdict, without loading unrelated files.

---

## MVP — the two-week slice (SPEC.md §9)

Resist building all six lenses. Prove the loop end to end on **five nodes** of
one real project (the `examples/greenfield/` project is that shape):

1. Manifest schema + validator
2. Extractor emitting `graph.json` (static only, no runtime yet)
3. tier0 eval runner
4. **One** rendered lens: health-coloured structure map
5. Click a node → see its manifest, version, last eval, claimed files
