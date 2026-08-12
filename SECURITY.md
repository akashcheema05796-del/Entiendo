# Security model

How Entiendo keeps an AI workload (or anyone else) from quietly changing the
things that judge it. Detail on the architecture: SPEC §17 (the oracle
boundary) and Invariant 9.

## Ground truth: the golden hash manifest

`entiendo/goldens.lock` pins the SHA-256 of every golden file in a project
root — both the datasets manifests declare and anything matching
`evals/**/golden*` on disk (so a planted-but-undeclared golden is caught as
an *addition*).

- **Runtime**: every grading path calls `integrity.ensure_verified()`; a
  mismatch raises `GoldenTamperError` and the eval is an ERROR, never a pass.
- **CI**: `.github/workflows/integrity.yml` runs `ent goldens verify` on
  every PR and push to main, `--require-lock` where a lock exists.
- **Re-pinning**: `ent goldens bless` regenerates the lock — loudly, and it
  refuses under CI (`ENTIENDO_CI=1`/`CI=1`), so the gate can never re-pin
  itself. The lock is a committed file: every legitimate change to ground
  truth is a reviewable PR diff.

**The trust root is git history + branch protection + CI review — not a key
an agent could read.** Hand-editing `goldens.lock` to match tampered files
produces a lock diff in the PR; that diff is what review exists to catch.

### What the manifest does NOT protect against

- A human approving and merging a bad PR. Review is the last gate; the
  manifest only guarantees the change is *visible*, never invisible.
- Tampering inside a single process after verification has cached (the check
  is once-per-process by design; CI re-verifies from disk).
- Meaning. The manifest pins *bytes*; whether the expected values are *right*
  is the per-dataset human blessing (`ent bless`, signature void on change)
  plus oracle-class provenance (`implementation-derived` rows quarantined).

### Planned upgrade path: Sigstore (design stub, not implemented)

When provenance beyond git is needed: CI signs `goldens.lock` with
`gh-action-sigstore-python` (keyless, OIDC identity = the repo's release
workflow), committing the detached bundle as `goldens.lock.sigstore`; runtime
verification then checks both the hash manifest *and* the signature's
identity claims (repo, workflow, ref). That moves the trust root from "this
repo's history" to "this repo's CI identity, publicly logged in Rekor".
Deferred until the PyPI/registry pipeline settles.

## The other layers (already enforced)

- **Oracle boundary** (Invariant 9): the claims hook fail-closes agent editor
  writes to `entiendo/history|baselines|steering`, the generated
  `graph.json`/`coverage.json`, `entiendo/goldens.lock`, and any blessed
  dataset. Writes that bypass the hook void the blessing signature.
- **Blessing** is TTY-gated with a real identity — CI and scripts cannot
  bless; agents may propose rows, never sign them.
- **Eval isolation**: sandboxed child with rlimits + wall-clock timeout; the
  effect probe reports observed fs/network/subprocess activity and fails a
  false `sideEffects: none`.
- **Supply chain**: releases publish via PyPI Trusted Publishing (OIDC, no
  stored tokens), with the publish action pinned to a full commit SHA and
  PEP 740 attestations; CI runs pip-audit and ships a CycloneDX SBOM.

## Reporting a vulnerability

Open a GitHub security advisory on this repository (Security → Advisories →
Report a vulnerability). Please do not file public issues for exploitable
problems.
