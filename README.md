# 🧠 Entiendo: Hybrid Codebase Visualizer & AI Agent

A hybrid, privacy-first agentic system for codebase visualization, RAG-powered querying, and atomic refactoring. Deeply orchestrated using LangGraph and styled with a precision Bento Grid aesthetic.

## 🚀 Key Features

- **Hybrid Inference**: Routes standard tasks to lightweight models and complex refactors to high-reasoning reasoning clusters.
- **Bento Grid Interface**: A high-density, polished UI that visualizes codebase health, complexity heatmaps, and streaming AI traces.
- **Pointer-Based State**: Uses a SQLite session store to manage large code context without bloating the orchestration graph.
- **Deterministic Refactoring**: Replaces fragile diff generation with structural SEARCH/REPLACE blocks for AST-level transformations.

## 🏗️ Architecture

- **Transport Layer**: TypeScript + Express + Socket.io (Real-time streaming).
- **Orchestration**: LangGraph (Cyclic workflows and state management).
- **Vision Layer**: React + Tailwind CSS + Motion (Bento Grid design).
- **Tooling**:
    - `diff_engine`: Structural SEARCH/REPLACE code modification.
    - `ast_chunker`: Metadata-rich codebase chunking.
    - `Qdrant`: High-performance vector storage for RAG (planned).

## 🛠️ Setup & Requirements

### Installation
```bash
npm install
```

### Environment Configuration
Copy `.env.example` to `.env` and configure your keys:
- `GEMINI_API_KEY`: Required for LLM orchestration (server-side).
- `VITE_GEMINI_API_KEY`: Required for client-side repo analysis.
- `NODE_ENV`: Set to `production` to serve from `/dist`.

### Running Development
```bash
npm run dev
```

### Type Check
```bash
npm run lint
```

## 🛡️ Privacy
This system follows a "Local-First" data policy. Code content is processed locally or in secured reasoning clusters. Identifiers and metadata are cached in a private SQLite instance (`.session_cache.db`).
