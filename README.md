# Entiendo: Vibe to Visual Coding

Turn natural-language vibes into live Mermaid diagrams, streamed explanations, and atomic code refactors — powered by LangGraph and Gemini.

## Key Features

- **Diagram Generation**: Ask for any diagram (flowchart, sequence, class, ER, dependency graph) and get real Mermaid output rendered instantly in the panel.
- **Hybrid Inference**: Routes standard tasks to lightweight models and complex refactors to high-reasoning clusters.
- **Live Token Streaming**: LLM responses stream token-by-token to the UI — the panel opens immediately with content appearing in real time.
- **RAG with Automatic Fallback**: Semantic search via Qdrant when available; falls back to an in-memory cosine-similarity store (no Qdrant required to run).
- **Pointer-Based State**: Uses a SQLite session store to manage large code context without bloating the orchestration graph.
- **Deterministic Refactoring**: SEARCH/REPLACE blocks for precise, reviewable code changes with an accept/reject diff viewer.
- **Clickable File Bubbles**: Every file in the repo is visualized as an interactive bubble — click to inspect raw content.

## Architecture

- **Transport Layer**: TypeScript + Express + Socket.io (real-time streaming).
- **Orchestration**: LangGraph — cyclic workflows with 5 intent types:
  - `macro_structure` — high-level architectural overview (markdown, streamed)
  - `micro_logic` — single-file UML / flow diagram (Mermaid)
  - `diagram` — explicit diagram requests; picks the best Mermaid type automatically
  - `deep_explanation` — RAG-enhanced deep-dive (markdown, streamed)
  - `refactor` — SEARCH/REPLACE code edits with diff viewer
- **Vision Layer**: React + Tailwind CSS + Motion.
- **Tooling**:
  - `diff_engine` — structural SEARCH/REPLACE code modification
  - `ast_chunker` — metadata-rich codebase chunking
  - `rag_indexer` — Qdrant vector store with in-memory cosine-similarity fallback
  - `token_emitter` — per-session EventEmitter bus for streaming LLM tokens to the socket layer

## Setup & Requirements

### Installation
```bash
npm install
```

### Environment Configuration
Copy `.env.example` to `.env` and configure:

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Server-side LLM + embeddings (Gemini 1.5 Flash/Pro, text-embedding-004) |
| `VITE_GEMINI_API_KEY` | Yes | Client-side repo analysis (Gemini 1.5 Flash) |
| `QDRANT_URL` | No | Qdrant vector store URL (default: `http://localhost:6333`). Falls back to in-memory search if unavailable. |
| `NODE_ENV` | No | Set to `production` to serve from `/dist` |

### Running (Development)
```bash
npm run dev
```

### Running (Production)
```bash
npm run build && NODE_ENV=production npm start
```

### Type Check
```bash
npm run lint
```

### Optional: Qdrant (for persistent vector search)
```bash
docker run -p 6333:6333 qdrant/qdrant
```
Without Qdrant, the RAG indexer automatically falls back to an in-memory cosine-similarity search — no configuration needed.

## Privacy
Local-First data policy. Code content is processed locally or in secured reasoning clusters. Identifiers and metadata are cached in a private SQLite instance (`.session_cache.db`), which is excluded from version control.
