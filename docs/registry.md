# Publishing Entiendo to the MCP Registry

The [MCP Registry](https://registry.modelcontextprotocol.io) is the official
catalog MCP clients (Claude Code, and a growing list of aggregators) read to
discover servers. Entiendo ships a [`server.json`](../server.json) at the repo
root so publishing is one authenticated command once the prerequisite lands.

**Status: prepared, not yet published.** Registry validation for a
`registryType: pypi` package requires the package to exist **on PyPI** — and
`entiendo` is not on PyPI yet (publishing is a maintainer act; `release.yml`
is wired for Trusted Publishing once the publisher is configured on pypi.org).
Everything below is ready so that publish day is mechanical.

## What is already in place

- **`server.json`** (repo root) — schema
  `2025-12-11`, name `io.github.akashdatageek/entiendo` (GitHub-authenticated
  publishers must use the `io.github.<username>/` namespace), one `pypi`
  package running the stdio server via
  `uvx --from "entiendo[mcp]" entiendo mcp --root <project>`.
- **The `entiendo` console script** — an alias of `ent` matching the package
  name, because `uvx <package>` looks for a script named after the package.
- **The ownership marker** — PyPI packages are verified by an
  `mcp-name: io.github.akashdatageek/entiendo` line in the package README;
  it is embedded in `README.md` as an HTML comment (invisible on GitHub and
  PyPI, visible to the validator).

## Publish day (maintainer checklist)

1. Release to PyPI first (tag → `release.yml` → Trusted Publishing). Confirm
   `pip install "entiendo[mcp]"` works from a clean environment.
2. Check the versions agree: `pyproject.toml`, `server.json` top-level
   `version`, and `server.json` `packages[0].version` must all match the
   released version.
3. Install the publisher CLI and authenticate as the GitHub user that owns
   the namespace:

   ```bash
   brew install mcp-publisher        # or download from the registry's releases page
   mcp-publisher login github        # device-code flow
   ```

4. From the repo root:

   ```bash
   mcp-publisher publish             # reads ./server.json, validates, publishes
   ```

5. Verify:

   ```bash
   curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=entiendo"
   ```

Each new release repeats steps 1–2 and 4 (bump both versions in
`server.json` alongside `pyproject.toml` — CI's version-consistency check
will remind you).

> Registry docs move fast. If `mcp-publisher publish` rejects the schema,
> check the current server.json spec at
> `modelcontextprotocol/registry` → `docs/reference/server-json/` and bump the
> `$schema` date. (This page was written against the 2025-12-11 schema,
> verified 2026-08-09.)
