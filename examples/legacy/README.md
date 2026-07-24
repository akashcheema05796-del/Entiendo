# Legacy example (unmanaged)

A small repo with **no Entiendo manifests** — the retrofit input (SPEC §12 v2).

```
legacy/
  orders/service.py    place_order() → calls catalog + ledger
  catalog/lookup.py     find()
  ledger/write.py       record()
  settings.yaml         config surface
```

Retrofit it:

```bash
cd examples/legacy
ent retrofit .                 # infer nodes → write proposals to entiendo/proposals/
ent retrofit accept --all      # promote them into place (node by node in practice)
ent validate                   # the accepted manifests validate
ent extract                    # the inferred graph reconciles
```

Expect to correct guesses — retrofit infers boundaries nobody declared, and it
will guess wrong often. The proposals are stubs (owner/contract/evals are TODO),
staged for human review, not written into the tree until you accept.

`entiendo/proposals/` and accepted `entiendo.node.yaml` files are git-ignored here
so the example stays a clean "unmanaged" starting point.
