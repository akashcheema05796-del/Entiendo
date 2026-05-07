# 🪐 Code Cosmos: Hybrid Codebase Visualizer & AI Agent

A hybrid, privacy-first agentic system for codebase visualization, RAG-powered querying, and atomic refactoring. Deeply orchestrated using LangGraph and styled with a precision Bento Grid aesthetic.

## 🚀 Key Features

- **Hybrid Inference**: Routes standard tasks to lightweight models and complex refactors to high-reasoning reasoning clusters.
- **Bento Grid Interface**: A high-density, polished UI that visualizes codebase health, complexity heatmaps, and streaming AI traces.
- **Pointer-Based State**: Uses a SQLite session store to manage large code context without bloating the orchestration graph.
- **Deterministic Refactoring**: Replaces fragile diff generation with structural SEARCH/REPLACE blocks and GritQL for AST-level transformations.

## 🏗️ Architecture

- **Transport Layer**: TypeScript + Express + Socket.io (Real-time streaming).
- **Orchestration**: LangGraph (Cyclic workflows and state management).
- **Vision Layer**: React + Tailwind CSS + Motion (Bento Grid design).
- **Tooling**:
    - `GritQL`: Structural AST transformations.
    - `Tree-sitter`: Metadata-rich codebase chunking.
    - `Qdrant`: High-performance vector storage for RAG.

## 🛠️ Setup & Requirements

### Installation
```bash
npm install
```

### Environment Configuration
Copy `.env.example` to `.env` and configure your keys:
- `GEMINI_API_KEY`: Required for LLM orchestration.
- `QDRANT_URL`: URL for the vector database.

### Running Development
```bash
npm run dev
```

## 🛡️ Privacy Shield
This system follows a "Local-First" data policy. Code content is processed locally or in secured reasoning clusters. Identifiers and metadata are cached in a private SQLite instance (`.session_cache.db`).
