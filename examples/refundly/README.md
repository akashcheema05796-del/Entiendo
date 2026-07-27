# refundly — the v4 reference project

A support-refund pipeline, laid out the Entiendo way. It is the fixture every
Universe (H2–H5) acceptance runs against.

```
parse_email (compute) ─▶ orders (state) ─▶ policy (config)
        └─▶ decide (agentic: interior tools + trajectory)
                 ├─▶ gateway.execute_refund (external · irreversible · approval)
                 └─▶ ledger (state · writes)
```

## Six units, every relevant kind

| Unit | Kind | Role |
|---|---|---|
| `refundly.parse_email` | compute | pull order id + reason out of the email |
| `refundly.orders` | state | look up an order's amount + age |
| `refundly.policy` | config | the refund thresholds the decider reads |
| `refundly.decide` | compute (agentic) | parse → look up → decide → refund → log |
| `refundly.gateway` | external | issue the refund — **irreversible, approval-gated** |
| `refundly.ledger` | state | record every case (**writes**) |

## What this example exercises

- **The agentic interior** — `decide` has five registry tools, each crossing to a
  declared edge; a **trajectory invariant** checks their order (parse → order_lookup
  → issue_refund → write_ledger).
- **The approval gate + irreversible side effect** — `gateway` is `irreversible`
  with `approval.required: true`.
- **Budgets + a blown one** — `gateway`'s cost budget (`$0.01/call`) is deliberately
  tight; the recorded traces spend `$0.05`, so the cost overlay has something amber.
- **Recorded traces** — three synthetic requests ship in
  `entiendo/history/events.jsonl` (tracked, not runtime): a happy refund, a deny,
  and a **bad-order** run where `issue_refund` fires before `order_lookup` (the
  trajectory-violation trace the Trace lens plays back).

## Run it

```bash
cd examples/refundly
ent validate
ent extract --check      # 6 units, edges reconcile, interior tools verified, 100% coverage
ent eval --all           # decide + parse_email GREEN; state/config/external UNTESTED
ent render               # the Universe, with interiors, traces, and the blown budget
```
