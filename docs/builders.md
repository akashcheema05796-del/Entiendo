# Using Entiendo in your builder

Entiendo speaks **MCP** (Model Context Protocol), so any editor or agent that
speaks MCP can read and write *through units* instead of free-roaming the file
tree. This page covers **Claude Code**, **Cursor**, and **Google Antigravity**,
plus the parts that are true everywhere.

---

## 0. Install the CLI first (all builders)

Every integration is the same one process — `ent mcp` — so the CLI has to be on
your PATH before any editor can start it.

```bash
# not on PyPI yet
pip install "entiendo[mcp] @ git+https://github.com/akashdatageek/Entiendo"
# or from a checkout
pip install -e ".[dev,mcp]"

ent --version        # → ent 0.2.0
ent doctor           # environment check: deps, extras, schema, project
```

The `[mcp]` extra is what makes `ent mcp` work; without it the server exits with
an install hint instead of starting.

> **Use an absolute path if your editor can't find `ent`.** GUI editors often
> don't inherit your shell's PATH (pyenv, conda, and `~/.local/bin` are the
> usual casualties). `which ent` → paste that path as the `command`.

### Just the map, with no editor integration at all

Worth knowing before you wire anything up: the map is useful on its own, in any
repo that has manifests.

```bash
cd /path/to/your/project
ent extract        # generate entiendo/graph.json + coverage.json
ent dev            # the Universe at http://127.0.0.1:7373, live-reloading
```

`ent render` instead writes a self-contained `entiendo/render.html` you can open
from disk or send to someone — no server, no network requests.

---

## 1. The universal registration

Every MCP-capable builder takes the same shape. One stdio server, eleven tools:

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

| Tool | What it does |
|---|---|
| `get_graph` | the whole map: units, edges, verdicts, versions, coverage |
| `get_node_context` | **scoped read** — one unit's manifest, its claimed file bodies, and neighbours' *contracts only* |
| `apply_edit` | **boundary-confined write** — paths outside the unit's claims are rejected, tier0 reruns |
| `revert_node` | restore the pre-edit backup |
| `run_eval` | run a unit's evals, get the verdict |
| `get_blast_radius` | what breaks if this unit changes |
| `validate_manifests` | schema + semantic validation |
| `retrofit_propose` / `retrofit_accept` | infer units for an unmanaged repo, one accepted at a time |
| `await_steering` / `post_verdict` | the Bridge: pick up an intent queued from the canvas, post the result back |

`--root .` means "the project the editor opened". Point it elsewhere with an
absolute path if you keep the map outside the repo.

---

## 2. What is universal, and what is not

This is the part worth reading before you choose.

| | Claude Code | Cursor | Antigravity | any other MCP client |
|---|---|---|---|---|
| the eleven tools | ✅ | ✅ | ✅ | ✅ |
| scoped reads (`get_node_context`) | ✅ | ✅ | ✅ | ✅ |
| **claims enforced on `apply_edit`** | ✅ | ✅ | ✅ | ✅ |
| **claims enforced on the agent's *own* edits** (pre-write hook) | ✅ | ✅ | ✅ | ❌ |
| one-command packaged install | ✅ plugin | manual (plugin format exists) | manual (plugin format exists) | ❌ |
| `entiendo-operator` / `entiendo-retrofit` skills | ✅ | paste the loop yourself | paste the loop yourself | ❌ |
| the Universe, `ent ci`, the whole CLI | ✅ | ✅ | ✅ | ✅ |

Two things are true everywhere:

**1. `apply_edit` refuses out-of-claims writes in every client.** That is
enforced inside Entiendo, not by the editor. Verified against a raw JSON-RPC
client with no editor involved at all:

```
error   : every path was outside the node's claims — nothing written
rejected: ['src/ledger/store.py']
hint    : propose a boundary change (edit the manifest's `claims`) …
```

**2. The agent's *own* edit tool can be blocked too — in all three editors.**
Each supports a hook that runs *before* a write and can refuse it. They disagree
only about the JSON, so one script speaks all three:

```bash
python3 .claude/hooks/enforce_claims.py --format claude       # default
python3 .claude/hooks/enforce_claims.py --format cursor
python3 .claude/hooks/enforce_claims.py --format antigravity
```

Same decision, three answer shapes (`permissionDecision` / `permission` /
`decision`). It **fails open** on anything it can't read — an unrecognised
payload, no `graph.json`, a missing `ent` — so it cannot brick a session.
`ENT_HOOK_DISABLE=1` turns it off entirely.

> Verified honestly: the decision logic and all three output shapes are covered
> by tests, and the Claude Code path is proven end to end in a live editor. The
> Cursor and Antigravity wirings are written against their published hook
> contracts but have **not** been run inside those editors here — if the payload
> shape differs in your version, the hook allows rather than blocks, and your CI
> gate still holds.

**Whatever the editor, CI is the backstop**, and it is a real one:

```bash
ent ci      # validate + reconcile + eval, one gate
```

Be precise about what that catches, because "CI covers it" is the kind of claim
worth checking. Adding an undeclared import from one unit into another fails the
build, naming the edge (measured — exit code 1):

```
FAIL  drift: undeclared dependency ent.history -> ent.surface
      (observed: src/ent/history.py imports render) — declare it or remove it
```

| Out-of-band edit | Caught by |
|---|---|
| reaches into another unit without declaring it | `ent extract --check` — **fails the build** |
| touches a file no unit claims | coverage — the file shows up unaccounted |
| breaks the unit's behaviour | its evals — `ent eval` / `ent ci` go RED |
| stays inside its claims and keeps behaviour | *nothing* — and that is fine; that is just editing |

What you lose without the hook is the *keystroke-level* refusal, not the
guarantee. The map still cannot silently drift from the code.

---

## 3. Claude Code

The fullest integration: MCP + both skills + the boundary hook, as one plugin.

```
/plugin marketplace add akashdatageek/Entiendo
/plugin install entiendo@entiendo-marketplace
```

For a local clone instead of GitHub:

```
/plugin marketplace add /absolute/path/to/Entiendo
/plugin install entiendo@entiendo-marketplace
```

Prefer per-project MCP only, with no plugin? Drop a `.mcp.json` at the repo root
with the universal JSON above and approve the server when prompted.

**What you get beyond the tools:**

- **`enforce_claims` hook** — on Edit/Write/MultiEdit, an edit to a file no unit
  claims is *mechanically denied*, and while a steer is active, so is an edit to
  a different unit's files. It **fails open** everywhere it can't be sure (no
  `graph.json`, malformed payload, missing `ent`), so it cannot brick an
  ordinary repo. `ENT_HOOK_DISABLE=1` is the escape hatch.
- **`entiendo-operator` skill** — say *"operate the map"* and Claude loops
  `await_steering` → `get_node_context` → `apply_edit` → `post_verdict`, driven
  from the Universe's Steer button.
- **`entiendo-retrofit` skill** — say *"retrofit this repo"* for a semantic
  boundary analysis that proposes units one at a time for your approval.

**The operator loop** (two terminals, one repo):

```bash
# terminal 1 — the canvas you steer from
ent serve --operator      # prints the exact command for terminal 2

# terminal 2 — the workload
claude
> operate the map
```

Click a unit, type an intent, hit **Steer**. Claude picks it up, edits *through
the unit*, reruns its evals, and the verdict lands back in the window. On a unit
with `approval.required`, the edit is held as a **proposal**: the diff is
captured, the working tree reverts, and nothing is live until you approve it.

---

## 4. Cursor

**Config file** — project `<project>/.cursor/mcp.json`, global
`~/.cursor/mcp.json`. Both are merged; on a name clash the project file wins.

```json
{
  "mcpServers": {
    "entiendo": {
      "type": "stdio",
      "command": "ent",
      "args": ["mcp", "--root", "${workspaceFolder}"]
    }
  }
}
```

`${workspaceFolder}` is resolved by Cursor as "the folder containing
`.cursor/mcp.json`", which is steadier than `.` if the agent's working directory
moves. `${env:NAME}` and `${userHome}` are available too.

> Cursor's field table marks `type` as required while its own examples omit it.
> Include it — it works either way and matches the documented schema.

**Or via the UI:** sidebar → **Customize** → **MCPs** → **Add to Cursor**. The
same panel toggles servers on and off.

**Approval:** MCP tools need approval by default. Settings → Agents →
**Approvals & Execution** picks the run mode (`Auto-review` is the default in
3.6+); finer rules live in `.cursor/permissions.json`.

**Boundary hook (optional, recommended).** Cursor's `preToolUse` hook can refuse
a write before it happens. Create `.cursor/hooks.json`:

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "matcher": "Write",
        "command": "python3 /absolute/path/to/Entiendo/.claude/hooks/enforce_claims.py --format cursor"
      }
    ]
  }
}
```

Set `"failClosed": true` on the hook if you would rather a hook crash block the
write than allow it. Entiendo's script fails **open** by design; that flag is
Cursor's own belt-and-braces.

---

## 5. Google Antigravity

**Config file** — global `~/.gemini/config/mcp_config.json`, workspace
`.agents/mcp_config.json`. (Those paths are documented for the **IDE** and
**CLI**. In Antigravity 2.0 the docs route you through the UI and do not state a
path — use Settings → **Customizations** → **Installed MCP Servers** → **Add
MCP** there, or check your version's docs.)

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

The inner object is the same shape as Cursor's, so a stdio entry copies across
cleanly. **Remote** servers do not: Antigravity requires `serverUrl` and
explicitly rejects `url`/`httpUrl`. Entiendo is stdio, so this doesn't bite —
but it is the usual reason a copied config silently fails.

Useful extras it supports on the same entry: `cwd`, `env`, `disabled`, and
`disabledTools` (withhold specific tools from the model).

**In the IDE:** **…** at the top of the agent panel → **MCP Servers** →
**Manage MCP Servers** → **View raw config** opens `mcp_config.json` directly.
**In the CLI:** type `/mcp` for the MCP manager overlay (status, reload, logs).

**Approval:** the permissions engine is Deny > Ask > Allow, and unconfigured MCP
tools default to **Ask**. Grant Entiendo blanket approval with an allow rule for
`mcp(entiendo/*)` if you trust the boundary (you should — every write it makes
is claims-checked).

**Boundary hook (optional, recommended).** `hooks.json` in `.agents/` (workspace)
or `~/.gemini/config/` (global). Note the shape differs from Cursor's — a named
hook object, PascalCase events, and `decision` rather than `permission`:

```json
{
  "entiendo-claims": {
    "PreToolUse": [
      {
        "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/Entiendo/.claude/hooks/enforce_claims.py --format antigravity",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Bundling it all.** Antigravity has a plugin layout that maps onto exactly what
Entiendo ships — drop a directory into `.agents/plugins/` (workspace) or
`~/.gemini/config/plugins/` (global):

```
plugins/entiendo/
├── plugin.json        # {"name": "entiendo"}
├── mcp_config.json    # the server entry above
├── hooks.json         # the PreToolUse hook above
└── skills/…           # port the operator/retrofit skills if you want them
```

---

## 6. Any other MCP client

Nothing above is special-cased. `ent mcp` is a plain stdio JSON-RPC server:
initialize, `notifications/initialized`, then `tools/list` returns all eleven.
If your tool can launch a command and speak MCP over stdin/stdout, it works.

```bash
# the crudest possible smoke test — no editor at all
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"x","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | ent mcp --root .
```

---

## 7. Prompts that actually use the map

Whatever the builder, these are the phrasings that route work through units:

| Say this | What it does |
|---|---|
| *"read unit `billing.invoices`"* | `get_node_context` — the unit's files plus neighbours' contracts, not the whole repo |
| *"change unit `billing.invoices` to …"* | `apply_edit` — confined to that unit's claims, evals rerun |
| *"what breaks if I change `billing.invoices`?"* | `get_blast_radius` |
| *"retrofit this repo"* | `retrofit_propose`, one unit at a time for your approval |
| *"is the map still true?"* | `validate_manifests` + `ent extract --check` |

---

## 8. Sanity checklist

If something feels wrong, these four answer "is the map still true?" in order:

```bash
ent doctor                 # environment: deps, extras, schema, project found
ent validate               # manifests conform to the schema
ent extract --check        # the graph reconciles with the code — no drift
ent ci                     # the one gate: validate + reconcile + eval
```

`ent ci` exits with a severity table: `0` pass · `1` RED/REGRESSED · `2` ERROR ·
`4` UNSTABLE/DEGRADED.

---

## 9. Honest limits

- **Eval *execution* is Python-only today.** Manifests, the graph, drift
  detection, coverage, and the Universe work for any language (TypeScript/JS
  import analysis included) — but running a unit against fixtures is Python, so
  a TS repo maps and reconciles while its units read *not checked yet*.
- **`ent serve` / `ent dev` bind `127.0.0.1` only** and require a CSRF token on
  every POST. It is a local operator surface, not a deployable service.
- **macOS and Linux are first-class.** On Windows the eval sandbox loses its
  rlimits (timeouts still apply) and history locking falls back to `msvcrt`;
  WSL2 is recommended.
- **The editor integrations add no tools beyond the eleven.** The windowed
  workspace is a *human* surface; it does not widen what an agent can do.

---

## Sources and freshness

The Cursor and Antigravity specifics on this page were taken from official
documentation on **2026-08-08**:
[cursor.com/docs/mcp](https://cursor.com/docs/mcp),
[cursor.com/docs/hooks](https://cursor.com/docs/hooks),
[antigravity.google/docs/mcp](https://antigravity.google/docs/mcp),
[antigravity.google/docs/hooks](https://antigravity.google/docs/hooks),
[antigravity.google/docs/plugins](https://antigravity.google/docs/plugins).

Both products move quickly. Two things were deliberately **not** written here
because they could not be confirmed from official docs: any tool-count cap (none
is documented for either — the widely repeated "40 tools" figure for Cursor is
not in current docs), and the config file path for Antigravity 2.0 specifically
(documented for the IDE and CLI only). If a path here doesn't match your
version, its own docs win.
