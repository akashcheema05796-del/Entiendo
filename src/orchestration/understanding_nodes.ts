import fs from 'fs';
import path from 'path';
import { GraphNode, GraphEdge, ProjectGraph } from '../types/project_graph.ts';
import { analyzeDependencies } from '../tools/dependency_analyzer.ts';
import { extractSymbols, extractCallEdges } from '../tools/symbol_extractor.ts';
import { emitRegistry } from '../infrastructure/emit_registry.ts';
import { store } from '../infrastructure/session_store.ts';

const CODE_EXTENSIONS: Record<string, string> = {
  '.ts': 'typescript', '.tsx': 'typescript',
  '.js': 'javascript', '.jsx': 'javascript',
  '.py': 'python',
  '.go': 'go',
  '.rs': 'rust',
  '.java': 'java',
  '.md': 'markdown',
  '.json': 'json',
  '.yaml': 'yaml', '.yml': 'yaml',
  '.toml': 'toml',
};
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.next', 'build', 'coverage', '.turbo']);

export interface UnderstandingState {
  sessionId: string;
  workspacePath: string;
  triggerKind: 'full_index' | 'incremental' | 'directory_expand';
  targetPath?: string;
  graphRef?: string;
  error?: string;
}

function emit(sessionId: string, event: string, data: unknown) {
  emitRegistry.emit(sessionId, event, data);
}

function makeNodeId(relativePath: string): string {
  return relativePath.replace(/\\/g, '/');
}

// ── Node 1: Walk the file system ─────────────────────────────────────────────

export async function fileWalkerNode(state: UnderstandingState): Promise<Partial<UnderstandingState>> {
  emit(state.sessionId, 'graph_progress', { phase: 'walking', pct: 0, detail: 'Scanning files...' });

  const rootPath = state.targetPath
    ? path.join(state.workspacePath, state.targetPath)
    : state.workspacePath;

  const fileNodes: GraphNode[] = [];
  const dirNodes: GraphNode[] = [];
  const containsEdges: GraphEdge[] = [];

  const walk = (dir: string, parentId: string | null) => {
    let entries: fs.Dirent[];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }

    for (const entry of entries) {
      if (SKIP_DIRS.has(entry.name)) continue;
      const fullPath = path.join(dir, entry.name);
      const relativePath = path.relative(state.workspacePath, fullPath).replace(/\\/g, '/');
      const nodeId = makeNodeId(relativePath);

      if (entry.isDirectory()) {
        dirNodes.push({ id: nodeId, kind: 'directory', label: entry.name, relativePath, language: 'directory', loc: 0, symbols: [] });
        if (parentId) containsEdges.push({ id: `${parentId}->${nodeId}:contains`, source: parentId, target: nodeId, kind: 'contains' });
        walk(fullPath, nodeId);
      } else {
        const ext = path.extname(entry.name).toLowerCase();
        const language = CODE_EXTENSIONS[ext] ?? 'unknown';
        let loc = 0;
        try { loc = fs.readFileSync(fullPath, 'utf-8').split('\n').length; } catch { /* skip */ }
        fileNodes.push({ id: nodeId, kind: 'file', label: entry.name, relativePath, language, loc, symbols: [] });
        if (parentId) containsEdges.push({ id: `${parentId}->${nodeId}:contains`, source: parentId, target: nodeId, kind: 'contains' });
      }
    }
  };

  walk(rootPath, null);
  emit(state.sessionId, 'graph_progress', { phase: 'walking', pct: 25, detail: `Found ${fileNodes.length} files, ${dirNodes.length} directories` });

  // Store intermediate result
  const ref = store.put({ fileNodes, dirNodes, containsEdges }, 3600);
  return { graphRef: ref };
}

// ── Node 2: Extract imports/exports (dependency edges) ────────────────────────

export async function dependencyAnalyzerNode(state: UnderstandingState): Promise<Partial<UnderstandingState>> {
  emit(state.sessionId, 'graph_progress', { phase: 'analyzing', pct: 30, detail: 'Analyzing dependencies...' });

  const intermediate = store.get(state.graphRef!) as { fileNodes: GraphNode[]; dirNodes: GraphNode[]; containsEdges: GraphEdge[] } | null;
  if (!intermediate) return { error: 'Intermediate graph data lost from store.' };

  const { fileNodes, dirNodes, containsEdges } = intermediate;

  // Read file contents for analysis (skip large files)
  const fileEntries = fileNodes
    .filter(n => n.language !== 'unknown' && n.language !== 'markdown')
    .map(n => {
      try {
        const content = fs.readFileSync(path.join(state.workspacePath, n.relativePath), 'utf-8');
        return { relativePath: n.relativePath, content: content.slice(0, 50_000), language: n.language };
      } catch { return null; }
    })
    .filter(Boolean) as { relativePath: string; content: string; language: string }[];

  const importEdges = analyzeDependencies(fileEntries);

  emit(state.sessionId, 'graph_progress', { phase: 'analyzing', pct: 55, detail: `Found ${importEdges.length} import relationships` });

  const ref = store.put({ fileNodes, dirNodes, containsEdges, importEdges, fileEntries }, 3600);
  return { graphRef: ref };
}

// ── Node 3: Extract symbols per file ─────────────────────────────────────────

export async function symbolExtractorNode(state: UnderstandingState): Promise<Partial<UnderstandingState>> {
  emit(state.sessionId, 'graph_progress', { phase: 'extracting', pct: 60, detail: 'Extracting symbols...' });

  const intermediate = store.get(state.graphRef!) as {
    fileNodes: GraphNode[];
    dirNodes: GraphNode[];
    containsEdges: GraphEdge[];
    importEdges: GraphEdge[];
    fileEntries: { relativePath: string; content: string; language: string }[];
  } | null;
  if (!intermediate) return { error: 'Intermediate data lost.' };

  const { fileNodes, dirNodes, containsEdges, importEdges, fileEntries } = intermediate;

  // Enrich file nodes with symbols
  const enrichedFileNodes = fileNodes.map(node => {
    const entry = fileEntries.find(e => e.relativePath === node.relativePath);
    if (!entry) return node;
    const symbols = extractSymbols(node.relativePath, entry.content, node.language);
    return { ...node, symbols };
  });

  emit(state.sessionId, 'graph_progress', { phase: 'extracting', pct: 80, detail: `Extracted symbols from ${enrichedFileNodes.length} files` });

  const ref = store.put({ fileNodes: enrichedFileNodes, dirNodes, containsEdges, importEdges }, 3600);
  return { graphRef: ref };
}

// ── Node 4: Assemble final ProjectGraph ──────────────────────────────────────

export async function graphBuilderNode(state: UnderstandingState): Promise<Partial<UnderstandingState>> {
  emit(state.sessionId, 'graph_progress', { phase: 'building', pct: 85, detail: 'Assembling graph...' });

  const intermediate = store.get(state.graphRef!) as {
    fileNodes: GraphNode[];
    dirNodes: GraphNode[];
    containsEdges: GraphEdge[];
    importEdges: GraphEdge[];
  } | null;
  if (!intermediate) return { error: 'Intermediate data lost.' };

  const { fileNodes, dirNodes, containsEdges, importEdges } = intermediate;

  // Assign initial layout positions (spiral layout for readability)
  const allNodes = [...dirNodes, ...fileNodes];
  const total = allNodes.length;
  allNodes.forEach((node, i) => {
    const angle = (i / total) * 2 * Math.PI * 3;
    const radius = 100 + i * 8;
    node.x = 800 + radius * Math.cos(angle);
    node.y = 500 + radius * Math.sin(angle);
  });

  // Only keep import edges where both source and target exist as nodes
  const nodeIds = new Set(allNodes.map(n => n.id));
  const validImportEdges = importEdges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

  const graph: ProjectGraph = {
    workspacePath: state.workspacePath,
    generatedAt: Date.now(),
    nodes: allNodes,
    edges: [...validImportEdges, ...containsEdges],
  };

  store.saveGraph(state.workspacePath, graph);

  const graphRef = store.put(graph, 7200);

  emit(state.sessionId, 'graph_progress', { phase: 'building', pct: 100, detail: 'Graph ready' });
  emit(state.sessionId, 'graph_ready', {
    nodeCount: graph.nodes.length,
    edgeCount: graph.edges.length,
    graphRef,
  });

  return { graphRef };
}

// ── Symbol expansion (on-demand when user clicks a file node) ────────────────

export function expandFileNode(
  workspacePath: string,
  node: GraphNode
): { childNodes: GraphNode[]; childEdges: GraphEdge[] } {
  try {
    const content = fs.readFileSync(path.join(workspacePath, node.relativePath), 'utf-8');
    const symbols = extractSymbols(node.relativePath, content, node.language);
    const callEdges = extractCallEdges(node.relativePath, symbols, content);

    const childNodes: GraphNode[] = symbols.map(sym => ({
      id: `${node.id}:${sym.name}`,
      kind: sym.kind === 'class' ? 'class' : sym.kind === 'interface' ? 'interface' : 'function',
      label: sym.name,
      relativePath: node.relativePath,
      language: node.language,
      loc: sym.endLine - sym.startLine,
      symbols: [],
      x: (node.x ?? 0) + (Math.random() - 0.5) * 80,
      y: (node.y ?? 0) + (Math.random() - 0.5) * 80,
    }));

    // Add contains edges from file → symbols
    const containsEdges: GraphEdge[] = childNodes.map(child => ({
      id: `${node.id}->${child.id}:contains`,
      source: node.id,
      target: child.id,
      kind: 'contains' as const,
    }));

    return { childNodes, childEdges: [...containsEdges, ...callEdges] };
  } catch {
    return { childNodes: [], childEdges: [] };
  }
}
