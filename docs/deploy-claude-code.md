# Deploying Entiendo in Claude Code

Three ways in, from lightest to fullest. All of them need the `ent` CLI on your
PATH first.

```bash
pip install "entiendo[mcp]"           # once published
# or, from a clone:
pip install -e ".[dev,mcp]"
ent --version
```

The `[mcp]` extra is what makes `ent mcp` work — without it the server exits
with an install hint rather than starting.

---

## 1. Just the map (no Claude Code integration)

Works in any repo that has manifests, with no plugin and no MCP:

```bash
cd /path/to/your/project
ent extract        # generate entiendo/graph.json + coverage.json
ent dev            # the Universe at http://127.0.0.1:7373, live-reloading
```

`ent render` instead of `ent dev` writes a self-contained
`entiendo/render.html` you can open from disk or email to someone — no server,
no network requests.

---

## 2. Per-project MCP server (one file, no install)

Drop a `.mcp.json` at the root of the project you want Claude Code to steer:

```json
{
  "mcpServers": {
    "entiendo": {
      "command": "ent",
      "args": ["mcp", "--root", "."]
    }
  }
}
```

Start `claude` in that directory and approve the server when prompted. You get
the eleven tools — `get_graph`, `get_node_context`, `run_eval`,
`get_blast_radius`, `apply_edit`, `revert_node`, `retrofit_propose`,
`retrofit_accept`, `validate_manifests`, and the Bridge pair
`await_steering` / `post_verdict`.

This is what the Entiendo repo itself ships, which is why Claude Code can
already operate this repo with no extra setup.

**What changes for you:** ask Claude to "read unit X" and it uses
`get_node_context` (scoped context — manifest, claimed file bodies, neighbour
*contracts* only) instead of grepping the whole tree. Ask it to change a unit
and `apply_edit` confines the write to that unit's `claims` and reruns tier0.

---

## 3. Full plugin (MCP + skills + boundary hook, everywhere)

The plugin bundles the MCP server, both skills, and the `enforce_claims` hook
so they follow you into any project.

```
/plugin marketplace add akashdatageek/Entiendo
/plugin install entiendo@entiendo-marketplace
```

For a local clone instead of GitHub:

```
/plugin marketplace add /absolute/path/to/Entiendo
/plugin install entiendo@entiendo-marketplace
```

You get:

| Piece | What it does |
|---|---|
| `entiendo` MCP server | the eleven tools above |
| `entiendo-operator` skill | say *"operate the map"* — Claude loops `await_steering` → `get_node_context` → `apply_edit` → `post_verdict`, driven from the Universe's Steer button |
| `entiendo-retrofit` skill | say *"retrofit this repo"* — semantic boundary analysis proposing units one at a time for your approval |
| `enforce_claims` hook | PreToolUse on Edit/Write/MultiEdit: an edit outside a unit's claims is **mechanically denied**, not politely discouraged |

### The hook is the part that changes behaviour

In a managed repo (one with `entiendo/graph.json`), the hook denies:

- edits to files no unit claims (`UNCLAIMED — no unit owns it`)
- edits to a *different* unit's files while a steer is active

It **fails open** everywhere else — no graph.json, malformed payload, missing
`ent` install, or plane-owned paths (manifests, `entiendo/`, `evals/`) all
allow. It cannot brick a session in an ordinary repo. `ENT_HOOK_DISABLE=1`
bypasses it entirely if you need an escape hatch.

---

## The operator loop (what this is actually for)

Two terminals, one repo:

```bash
# terminal 1 — the canvas you steer from
ent serve --operator      # prints the exact command for terminal 2

# terminal 2 — the workload
claude
> operate the map
```

Click a unit in the browser, type an intent, hit **Steer**. Claude Code picks
it up, edits *through the unit*, reruns its evals, and the dossier flips from
"queued" to the verdict — with no terminal typing on the operator's side. On a
unit with `approval.required`, the edit lands as a **proposal**: the diff is
captured, the working tree reverts, and nothing is live until you approve it in
the browser.

---

## Sanity checklist

```bash
ent doctor                 # environment check
ent validate               # manifests conform to the schema
ent extract --check        # graph reconciles, no drift (CI mode)
ent ci                     # the one gate: validate + reconcile + eval + tier1
```

`ent ci` exits with the severity table: `0` pass · `1` RED/REGRESSED · `2`
ERROR · `4` UNSTABLE/DEGRADED.

---

## Notes and honest limits

- **Python only for execution.** Manifests, the graph, drift detection, and the
  Universe work for any language (TypeScript/JS import analysis included). But
  tier0/tier1 *execution* — running a unit against fixtures — is Python-only
  today, so a TS repo maps and reconciles but reads `UNTESTED`.
- **macOS/Linux first-class.** On Windows the eval sandbox loses its rlimits
  (timeouts still apply) and history locking falls back to `msvcrt`; WSL2 is
  recommended.
- **`ent serve`/`ent dev` bind 127.0.0.1 only** and require a CSRF token on
  every POST. It is a local operator surface, not a deployable web service.
- **The plugin adds no new MCP tools beyond the eleven** — windows and the
  workspace surface are a human surface (asserted by `test_no_new_mcp_tools_in_v7`).
