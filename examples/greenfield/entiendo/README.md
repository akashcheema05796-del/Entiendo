# `entiendo/` — generated artifacts

Everything here is **generated, never hand-edited** (SPEC.md §12). It is checked
in so the map is reproducible per commit, but only `ent` writes it.

| File / dir | Written by | Contents |
|---|---|---|
| `graph.json` | `ent extract` (L1) | Node topology + verified edges |
| `coverage.json` | `ent extract` (L1) | Claimed vs unclaimed files; coverage headline |
| `baselines/` | `ent eval` (L2/L3) | Eval baselines per node version |
| `history/` | history store (L3) | Append-only version + eval event log |

`graph.json` and `coverage.json` are git-ignored in this demo (see
`../.gitignore`) because no extractor exists yet — they appear the first time you
run `ent extract`. Never resolve a merge conflict inside them by hand; re-run the
extractor instead.
