import { tool } from '@langchain/core/tools';
import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import { ragIndexer } from './rag_indexer.ts';
import { store } from '../infrastructure/session_store.ts';
import { ProjectGraph } from '../types/project_graph.ts';

const CODE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.rs', '.java', '.cpp', '.c', '.md', '.json', '.yaml', '.yml', '.toml', '.env.example']);
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.next', 'build']);

function safeResolvePath(repoPath: string, relativePath: string): string | null {
  const resolved = path.resolve(path.join(repoPath, relativePath));
  if (!resolved.startsWith(path.resolve(repoPath))) return null;
  return resolved;
}

export function makeAgentTools(repoPath: string, sessionId: string, graphRef?: string | null) {
  const read_file = tool(
    async ({ file_path }) => {
      const full = safeResolvePath(repoPath, file_path);
      if (!full) return 'Access denied: path traversal detected.';
      try {
        const content = fs.readFileSync(full, 'utf-8');
        return content.slice(0, 8000) + (content.length > 8000 ? '\n... [truncated]' : '');
      } catch {
        return `File not found: ${file_path}`;
      }
    },
    {
      name: 'read_file',
      description: 'Read the full content of a file in the repository. Use this to understand specific implementation details.',
      schema: z.object({
        file_path: z.string().describe('Relative path from repo root, e.g. "src/index.ts"'),
      }),
    }
  );

  const list_files = tool(
    async ({ dir = '' }) => {
      const full = safeResolvePath(repoPath, dir);
      if (!full) return 'Access denied.';
      try {
        const entries = fs.readdirSync(full, { withFileTypes: true });
        return entries
          .filter(e => !SKIP_DIRS.has(e.name))
          .map(e => `${e.isDirectory() ? '[dir] ' : '[file]'} ${e.name}`)
          .join('\n') || '(empty directory)';
      } catch {
        return `Cannot list directory: ${dir || '/'}`;
      }
    },
    {
      name: 'list_files',
      description: 'List files and subdirectories at a given path. Start with "" to see the repo root.',
      schema: z.object({
        dir: z.string().optional().describe('Relative directory path. Defaults to repo root.'),
      }),
    }
  );

  const search_codebase = tool(
    async ({ query }) => {
      const chunks = await ragIndexer.retrieve(query, sessionId, 6);
      if (chunks.length === 0) return 'No semantically relevant code found. Try grep_codebase or read_file instead.';
      return chunks.join('\n\n---\n');
    },
    {
      name: 'search_codebase',
      description: 'Semantic vector search across all indexed code. Best for conceptual queries like "how is auth handled" or "where is caching done".',
      schema: z.object({
        query: z.string().describe('Natural language description of what you are looking for'),
      }),
    }
  );

  const grep_codebase = tool(
    async ({ pattern, dir = '' }) => {
      const target = safeResolvePath(repoPath, dir);
      if (!target) return 'Access denied.';
      const results: string[] = [];
      const walk = (d: string) => {
        try {
          for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
            if (SKIP_DIRS.has(entry.name)) continue;
            const full = path.join(d, entry.name);
            if (entry.isDirectory()) { walk(full); continue; }
            if (!CODE_EXTENSIONS.has(path.extname(entry.name))) continue;
            try {
              const lines = fs.readFileSync(full, 'utf-8').split('\n');
              lines.forEach((line, i) => {
                if (line.toLowerCase().includes(pattern.toLowerCase())) {
                  results.push(`${path.relative(repoPath, full)}:${i + 1}: ${line.trim()}`);
                }
              });
            } catch { /* skip unreadable */ }
          }
        } catch { /* skip inaccessible dirs */ }
      };
      walk(target);
      if (results.length === 0) return `No matches for "${pattern}".`;
      return results.slice(0, 40).join('\n') + (results.length > 40 ? `\n... (${results.length - 40} more matches)` : '');
    },
    {
      name: 'grep_codebase',
      description: 'Search for an exact text pattern across all code files. Best for finding function names, variable names, imports, or specific strings.',
      schema: z.object({
        pattern: z.string().describe('Text pattern to search for (case-insensitive)'),
        dir: z.string().optional().describe('Subdirectory to limit the search. Defaults to entire repo.'),
      }),
    }
  );

  const get_graph_context = tool(
    async ({ node_ids }) => {
      if (!graphRef) return 'No graph available for this session.';
      const graph = store.get(graphRef) as ProjectGraph | null;
      if (!graph) return 'Graph not found in store.';
      const ids = node_ids.length > 0 ? new Set(node_ids) : null;
      const nodes = ids ? graph.nodes.filter(n => ids.has(n.id)) : graph.nodes.slice(0, 30);
      const edges = ids
        ? graph.edges.filter(e => ids.has(e.source) || ids.has(e.target))
        : graph.edges.slice(0, 60);
      const nodeLines = nodes.map(n => `  [${n.kind}] ${n.relativePath} (${n.language}, ${n.loc} lines)`);
      const edgeLines = edges.map(e => `  ${e.source} --[${e.kind}]--> ${e.target}`);
      return `Nodes:\n${nodeLines.join('\n')}\n\nRelationships:\n${edgeLines.join('\n')}`;
    },
    {
      name: 'get_graph_context',
      description: 'Get the project graph topology — nodes (files, classes, functions) and their relationships (imports, calls, contains). Pass node_ids to filter to specific nodes, or empty array for a broad overview.',
      schema: z.object({
        node_ids: z.array(z.string()).describe('Node IDs to focus on. Pass [] for a broad overview.'),
      }),
    }
  );

  return [read_file, list_files, search_codebase, grep_codebase, get_graph_context] as const;
}

export type AgentTools = ReturnType<typeof makeAgentTools>;
