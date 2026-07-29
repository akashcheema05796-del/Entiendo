# Wiring `ent ci` as a status check

`ent ci` is the one gate to run in CI or a pre-commit hook. It runs the three
checks that already exist and collapses them to a single pass/fail:

1. **validate** — every `entiendo.node.yaml` conforms to the schema (L0)
2. **reconcile** — the graph matches reality; no undeclared edges / drift (L1)
3. **eval** — tier0 executes every unit; no `RED` or `ERROR` (L2 / Phase 7)

```
$ ent ci
entiendo ci

  ✓ validate   5 manifest(s) valid
  ✓ reconcile  no drift, coverage 100%
  ✓ eval       2 green, 3 untested, 0 red, 0 error

✓ ent ci passed
```

Exit code is `0` on pass, `1` on any gate failure, `2` on an environment problem
— so it drops straight into a CI step or a hook.

## GitHub Actions

```yaml
name: entiendo
on: [push, pull_request]
jobs:
  ent-ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -e '.[dev]'
      - run: ent ci            # ← the whole gate, one step
```

Make it a required status check in branch protection to block merges when a unit
goes RED or the graph drifts.

## Pre-commit

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: ent-ci
      name: ent ci
      entry: ent ci
      language: system
      pass_filenames: false
```

## Progressive adoption

A repo still being brought under management can run `ent ci --soft`: drift is
reported as a warning instead of failing the build (structural errors — a
double-claimed file, a dependency on an unknown unit — still fail). Drop `--soft`
once the graph is honest. See `ent extract --soft`.

To **ratchet coverage up**, add `--min-coverage <pct>`: the build fails while
claimed+acknowledged coverage is below the threshold, so a migrating team raises
the number over time (`ent ci --soft --min-coverage 60`, then 70, …). Works on
`ent extract` too. A `coverage` stage appears in the `ent ci` output when set.
