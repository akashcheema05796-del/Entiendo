# The interactive edit surface (`ent serve`)

The scoped edit loop (SPEC.md §6) made interactive: click a node, describe a
change, and an LLM edits it — confined to the node's claimed files — while tier0
reruns and the verdict, blast radius, and approval gate update live.

```bash
pip install -e '.[serve]'      # installs the anthropic SDK (the editing model)
export ANTHROPIC_API_KEY=...   # or `ant auth login`
cd examples/greenfield
ent serve                      # → http://127.0.0.1:7373
```

## Architecture

A thin backend over functions that already exist, plus a self-contained frontend.

| Layer | What |
|---|---|
| **Frontend** (`server.build_app_html`) | One HTML page (inline CSS/JS, no build step). Left: the node list coloured by health. Right: the selected node's context, eval buttons, and an edit box. |
| **Backend** (`server.handle_api`) | stdlib `http.server` — no new runtime dependency. A pure router so it's unit-tested without a socket. |
| **Model** (`agent.propose_edit`) | Claude Opus 5 via the official `anthropic` SDK, structured outputs. Optional — degrades to a clear 503 without it. |

### Endpoints

| Route | Does | Writes? |
|---|---|---|
| `GET /api/graph` | `build_view` — the six-lens model | no |
| `GET /api/node/{id}/context` | `assemble_context` — scoped context | no |
| `POST /api/node/{id}/eval` | `run_tier0` / `run_tier1` | no |
| `POST /api/node/{id}/edit` | propose (LLM) → **write within claims** → rerun tier0 → boundary + blast + approval | claims only |
| `POST /api/node/{id}/revert` | restore the pre-edit backup | claims only |

## Guarantees

- **The map is read-only** (Invariant 2). Only `/edit` and `/revert` write, and
  `/edit` writes **only within the node's claims**: `agent.propose_edit` rejects
  any file the model returns outside the claims, and `review_edit` re-checks the
  boundary. A boundary violation is surfaced, never applied.
- **Every edit is gated.** After the write, tier0 reruns and the response carries
  the verdict (GREEN/RED/UNTESTED/ERROR), the downstream **blast radius**, and the
  **approval** status (`ready-to-merge` / `awaiting-signoff` / `blocked`). A red
  edit is blocked; the pre-edit content is backed up for one-click revert.
- **No hard dependency.** The HTTP layer is stdlib. The model is an extra — with
  no SDK or credentials the explorer and manual evals work and the edit box
  returns a clear message.

## The loop, in the UI

1. Click a node → its manifest, claimed files, neighbour contracts, and recent
   evals load (the model's context window, made visible).
2. Run tier0/tier1 to see the current verdict.
3. Type a change ("clamp scores into [0,1]") → **propose & apply**.
4. The model edits within claims; tier0 reruns; the verdict, blast radius, and a
   before/after diff appear. Revert if it went red.
