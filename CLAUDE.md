# Entiendo — rules for Claude Code

Entiendo makes the **node** (not the file tree) the unit of work: a declared
component with a contract, a composite version, tiered evals, and history.
`SPEC.md` is the source of truth; this file is the enforcement summary.

## Invariants you must never break

1. **The map is generated, never drawn.** `entiendo/graph.json` and
   `entiendo/coverage.json` are build artifacts — never hand-edit them, never
   resolve merge conflicts inside them (regenerate with `ent extract`).
2. **Entiendo is a read-only observer** — never in any request path.
3. **No node without a contract; no contract without a tier-0 eval.**
4. **Every file is claimed by exactly one node or explicitly unclaimed.**
5. **Manifests are verified, not trusted.** Adding a real dependency means
   declaring it in the manifest too, or `ent extract --check` fails the build.
6. **Secrets are never rendered** — reference only.
7. **Health = baseline + significance threshold**, never a raw score.
8. **Edit through the node.** Use the Entiendo MCP tools (`get_node_context`,
   `apply_edit`) rather than free-roaming the repo when changing managed nodes.
   `apply_edit` rejects writes outside a node's `claims` — if you need to touch
   an unclaimed file, propose a boundary change (amend `claims` in the manifest)
   and get explicit human sign-off first.

## Eval authorship (the bootstrapping trap)

- You may author **tier0** evals freely (schema / invariant / smoke / trajectory).
- You may **propose** tier1 golden rows; only a human sets `humanBlessed: true`
  (`ent bless`). Never bless your own data.
- tier2 rubrics are human-owned; refine only on request.
- Baselines update only on human confirmation (`ent baseline`).

## Workflow

- Build order is strict L0 → L5 (SPEC §8). Don't start a later phase before the
  earlier one's acceptance criteria pass.
- After any edit to a managed node: tier0 must be green before you call it done.
  `ent eval <node-id>` locally; CI runs pytest + `ent validate` +
  `ent extract --check` on every PR.
- Retrofitting an unmanaged repo → use the `entiendo-retrofit` skill. One
  proposal at a time; the human accepts each.
- The manifest schema (`schemas/node.schema.json`, `apiVersion: entiendo/v1`)
  is the contract for the whole system — change it deliberately and version it.

## Stack constraints

- Runtime deps stay minimal (pyyaml, jsonschema); heavier deps live behind
  optional extras. Prefer boring, inspectable storage (git, JSON, Parquet/DuckDB)
  over services. Stdlib `http.server` for serving — no web framework.
- `pip install -e ".[dev]"` then `python -m pytest -q` (129+ tests, ~1.5s).

## MCP

`.mcp.json` registers `ent mcp` (stdio). Tools: `get_graph`,
`get_node_context`, `run_eval`, `get_blast_radius`, `apply_edit`,
`revert_node`, `retrofit_propose`, `retrofit_accept`, `validate_manifests`,
and the Bridge pair `await_steering` / `post_verdict`.
The visual surface is `ent serve` (the Universe, browser, port 7373); start it
when the user wants to *see* the map. To act as the workload the operator steers
from that canvas, use the `entiendo-operator` skill (`ent serve --operator`
prints the exact start command): loop `await_steering` → `get_node_context` →
`apply_edit` → `post_verdict`, editing through units, never around their claims.
