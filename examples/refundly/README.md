# refundly — the v3 reference project

A support-refund agent, laid out the Entiendo way. It grows phase by phase as the
vehicle for v3 features; **Phase D** introduces its agentic unit.

```
refundly.decide     compute · AGENTIC — look up the order, decide, (maybe) refund
  ├─ order_lookup  ─crosses→  refundly.orders     state
  └─ issue_refund  ─crosses→  refundly.gateway    external · irreversible · approval
```

## What this example demonstrates (Phase D)

- **Agentic unit** (`refundly.decide`) with an `interior:` block — a `process`, a
  **tool registry** (`order_lookup`, `issue_refund`), and `maxSteps`. Neighbours
  see its contract, never its interior (the law: still independently evaluable).
- **Trajectory invariant** (a reflex/tier0 eval) — the *path* is checked, not just
  the answer: `order_lookup` must precede `issue_refund`, no tool outside the
  registry, within the step bound. Evaluated against a recorded run log
  (`evals/refundly.decide/trajectory.jsonl`), deterministic and <1s.
- **Reconciled tools** — each `interior.tools[].crosses` must have a matching
  declared dependency edge. Drop the edge and `ent extract --check` fails naming
  the unit *and* the tool (Invariant 5).
- **Runtime guard** — `ent.guard(REGISTRY)` in `src/decide/agent.py` raises on an
  out-of-registry call, so the border the reconciler enforces at build time also
  holds at runtime (still read-only — it guards the workload).
- **Approval gate** — `refundly.gateway` is `irreversible` with
  `approval.required: true`.

## Run it

```bash
cd examples/refundly
ent validate
ent extract --check          # 3 units, edges reconcile, interior tools verified
ent eval --all               # refundly.decide → GREEN (invariants + smoke + trajectory)
```

To see the trajectory catch a bad path, reorder `trajectory.jsonl` so
`issue_refund` comes first, then re-run `ent eval refundly.decide` → **RED**,
naming the violated ordering.
