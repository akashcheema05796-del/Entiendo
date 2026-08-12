# Releasing entiendo

Releases publish to PyPI via **Trusted Publishing** (OIDC) — no token exists
anywhere. The pipeline is `.github/workflows/release.yml`, triggered only by a
version tag, with the publish action pinned to a full commit SHA and PEP 740
attestations enabled.

## One-time setup (human, in a browser)

On <https://pypi.org/manage/account/publishing/> add a **pending publisher**
for project `entiendo`:

| field | value |
|---|---|
| Owner | `akashdatageek` |
| Repository | `Entiendo` |
| Workflow | `release.yml` |
| Environment | `pypi` |

Until this exists, tag pushes still build and attach artifacts + SBOM; only
the publish job fails. (Optional: a second pending publisher on
<https://test.pypi.org> with environment `testpypi` if a TestPyPI rehearsal
job is ever added.)

## Cutting a release

1. Bump the version in **three places** (a test pins them together —
   `tests/test_registry.py::test_versions_agree_everywhere`):
   - `pyproject.toml` → `version`
   - `server.json` → top-level `version` AND `packages[0].version`
2. Move the `## Unreleased` section of `CHANGELOG.md` under the new version
   heading with today's date.
3. Verify locally:

   ```bash
   python -m pytest -q
   rm -rf dist && python -m build && twine check dist/*
   ```

4. Merge that PR to `main`, then tag **the merge commit**:

   ```bash
   git checkout main && git pull
   git tag v0.2.0            # match pyproject exactly, with the leading v
   git push origin v0.2.0
   ```

5. Watch the `Release` workflow: `build` → `publish` (environment `pypi`).
6. Confirm from a clean machine:

   ```bash
   pip install entiendo && ent --version
   ```

7. After the first successful PyPI release, publish to the MCP Registry —
   the checklist is [`docs/registry.md`](./docs/registry.md).

## Rules

- Never publish with a token; Trusted Publishing only.
- Never bump the pinned `gh-action-pypi-publish` SHA casually — it is the one
  action that touches PyPI. Bump deliberately and note the version in the
  comment beside it.
- A tag that doesn't match `pyproject.toml`'s version is a mistake; delete the
  tag, fix, re-tag.
