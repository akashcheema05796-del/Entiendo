import fs from 'fs';
import path from 'path';

const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.next', 'build', 'coverage']);
const CODE_EXTS = new Set(['.ts', '.tsx', '.js', '.jsx', '.py']);

// ── Types ──────────────────────────────────────────────────────────────────────

export type NodeType = 'file' | 'function' | 'class' | 'interface' | 'const';
export type EdgeType = 'imports' | 'calls' | 'extends' | 'defines';

export interface GNode {
  id: string;
  type: NodeType;
  file: string;   // relative path
  name: string;
  exported: boolean;
}

export interface GEdge {
  from: string;
  to: string;
  type: EdgeType;
}

interface CodeGraph {
  nodes: Map<string, GNode>;
  edges: GEdge[];
  outEdges: Map<string, GEdge[]>;
  inEdges: Map<string, GEdge[]>;
}

// ── Import resolver ────────────────────────────────────────────────────────────

function resolveImport(fromFile: string, importPath: string, repoPath: string): string | null {
  if (!importPath.startsWith('.')) return null; // skip external packages

  const fromDir = path.dirname(path.join(repoPath, fromFile));
  const resolved = path.resolve(fromDir, importPath);
  const rel = path.relative(repoPath, resolved);

  const candidates = ['', '.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.tsx', '/index.js', '/index.jsx'];
  for (const ext of candidates) {
    const candidate = rel + ext;
    try {
      if (fs.statSync(path.join(repoPath, candidate)).isFile()) return candidate;
    } catch { /* not found */ }
  }
  return rel; // best-effort even if file doesn't exist
}

// ── TS/JS parser ───────────────────────────────────────────────────────────────

function parseJSTS(content: string, relPath: string, repoPath: string): { nodes: GNode[]; edges: GEdge[] } {
  const fileId = relPath;
  const nodes: GNode[] = [{ id: fileId, type: 'file', file: relPath, name: path.basename(relPath), exported: true }];
  const edges: GEdge[] = [];
  const knownSymbols = new Set<string>();

  for (const raw of content.split('\n')) {
    const line = raw.trim();

    // ── Imports ──────────────────────────────────────────────────────────────
    const importSrc =
      (line.match(/^import\s+(?:type\s+)?.*?\s+from\s+['"]([^'"]+)['"]/) ||
       line.match(/^import\s+['"]([^'"]+)['"]/) ||
       line.match(/^(?:const|let|var)\s+\w+\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)/)
      )?.[1];

    if (importSrc) {
      const resolved = resolveImport(relPath, importSrc, repoPath);
      if (resolved) edges.push({ from: fileId, to: resolved, type: 'imports' });
    }

    // ── Function definitions ──────────────────────────────────────────────────
    const fnMatch =
      line.match(/^(export\s+(?:default\s+)?)?(async\s+)?function\s+(\w+)/) ||
      line.match(/^(export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(/) ||
      line.match(/^(export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?function/);

    if (fnMatch) {
      const isExported = !!(fnMatch[1]);
      const name = fnMatch[3] ?? fnMatch[2];
      if (name && /^[A-Za-z_$]/.test(name)) {
        const symId = `${fileId}::${name}`;
        if (!nodes.find(n => n.id === symId)) {
          nodes.push({ id: symId, type: 'function', file: relPath, name, exported: isExported });
          edges.push({ from: fileId, to: symId, type: 'defines' });
          knownSymbols.add(name);
        }
      }
    }

    // ── Class definitions ─────────────────────────────────────────────────────
    const classMatch = line.match(/^(export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?/);
    if (classMatch) {
      const isExported = !!(classMatch[1]);
      const name = classMatch[2];
      const parent = classMatch[3];
      const symId = `${fileId}::${name}`;
      if (!nodes.find(n => n.id === symId)) {
        nodes.push({ id: symId, type: 'class', file: relPath, name, exported: isExported });
        edges.push({ from: fileId, to: symId, type: 'defines' });
        knownSymbols.add(name);
        if (parent) edges.push({ from: symId, to: `__unresolved__::${parent}`, type: 'extends' });
      }
    }

    // ── Interface definitions ─────────────────────────────────────────────────
    const ifaceMatch = line.match(/^(export\s+)?interface\s+(\w+)(?:\s+extends\s+(\w+))?/);
    if (ifaceMatch) {
      const isExported = !!(ifaceMatch[1]);
      const name = ifaceMatch[2];
      const symId = `${fileId}::${name}`;
      if (!nodes.find(n => n.id === symId)) {
        nodes.push({ id: symId, type: 'interface', file: relPath, name, exported: isExported });
        edges.push({ from: fileId, to: symId, type: 'defines' });
        knownSymbols.add(name);
      }
    }
  }

  // ── Call detection (second pass over known symbols) ───────────────────────
  for (const raw of content.split('\n')) {
    const line = raw.trim();
    // Skip definition lines
    if (/^(?:export\s+)?(?:async\s+)?function|^(?:export\s+)?class|^(?:export\s+)?interface|^(?:export\s+)?const\s+\w+\s*=/.test(line)) continue;

    for (const sym of knownSymbols) {
      const callRe = new RegExp(`\\b${sym}\\s*[(<]`);
      if (callRe.test(line)) {
        edges.push({ from: fileId, to: `${fileId}::${sym}`, type: 'calls' });
      }
    }
  }

  return { nodes, edges };
}

// ── Python parser ──────────────────────────────────────────────────────────────

function parsePython(content: string, relPath: string, repoPath: string): { nodes: GNode[]; edges: GEdge[] } {
  const fileId = relPath;
  const nodes: GNode[] = [{ id: fileId, type: 'file', file: relPath, name: path.basename(relPath), exported: true }];
  const edges: GEdge[] = [];

  for (const raw of content.split('\n')) {
    const line = raw.trim();

    const fromImport = line.match(/^from\s+(\S+)\s+import/);
    if (fromImport) {
      const mod = fromImport[1].replace(/\./g, '/');
      const resolved = resolveImport(relPath, `./${mod}`, repoPath);
      if (resolved) edges.push({ from: fileId, to: resolved, type: 'imports' });
    }

    const fnMatch = line.match(/^def\s+(\w+)\s*\(/);
    if (fnMatch) {
      const name = fnMatch[1];
      const symId = `${fileId}::${name}`;
      nodes.push({ id: symId, type: 'function', file: relPath, name, exported: !name.startsWith('_') });
      edges.push({ from: fileId, to: symId, type: 'defines' });
    }

    const classMatch = line.match(/^class\s+(\w+)(?:\((\w+)\))?/);
    if (classMatch) {
      const name = classMatch[1];
      const parent = classMatch[2];
      const symId = `${fileId}::${name}`;
      nodes.push({ id: symId, type: 'class', file: relPath, name, exported: !name.startsWith('_') });
      edges.push({ from: fileId, to: symId, type: 'defines' });
      if (parent) edges.push({ from: symId, to: `__unresolved__::${parent}`, type: 'extends' });
    }
  }

  return { nodes, edges };
}

// ── GraphIndexer ───────────────────────────────────────────────────────────────

export class GraphIndexer {
  private graphs = new Map<string, CodeGraph>();
  private indexingPromises = new Map<string, Promise<void>>();

  waitForGraph(sessionId: string): Promise<void> {
    return this.indexingPromises.get(sessionId) ?? Promise.resolve();
  }

  indexRepo(repoPath: string, sessionId: string, onProgress?: (msg: string) => void): Promise<void> {
    let resolve!: () => void;
    const gate = new Promise<void>(r => { resolve = r; });
    this.indexingPromises.set(sessionId, gate);
    this._indexRepo(repoPath, sessionId, onProgress).finally(resolve);
    return gate;
  }

  private async _indexRepo(repoPath: string, sessionId: string, onProgress?: (msg: string) => void): Promise<void> {
    onProgress?.('[Graph] Building knowledge graph...');

    const allNodes = new Map<string, GNode>();
    const rawEdges: GEdge[] = [];
    const files = this.getCodeFiles(repoPath);

    onProgress?.(`[Graph] Parsing ${files.length} files for symbol extraction...`);

    for (const filePath of files) {
      try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const relPath = path.relative(repoPath, filePath);
        const ext = path.extname(filePath);

        const { nodes, edges } = ['.ts', '.tsx', '.js', '.jsx'].includes(ext)
          ? parseJSTS(content, relPath, repoPath)
          : parsePython(content, relPath, repoPath);

        for (const node of nodes) allNodes.set(node.id, node);
        rawEdges.push(...edges);
      } catch { /* skip unreadable files */ }
    }

    // Resolve __unresolved__ extends edges against the global symbol table
    const edges = rawEdges
      .map(edge => {
        if (!edge.to.startsWith('__unresolved__::')) return edge;
        const symbolName = edge.to.slice('__unresolved__::'.length);
        const resolved = [...allNodes.values()].find(n => n.name === symbolName && n.type !== 'file');
        return resolved ? { ...edge, to: resolved.id } : null;
      })
      .filter((e): e is GEdge => e !== null && !e.to.startsWith('__unresolved__'));

    // Build adjacency maps
    const outEdges = new Map<string, GEdge[]>();
    const inEdges = new Map<string, GEdge[]>();
    for (const edge of edges) {
      if (!outEdges.has(edge.from)) outEdges.set(edge.from, []);
      if (!inEdges.has(edge.to)) inEdges.set(edge.to, []);
      outEdges.get(edge.from)!.push(edge);
      inEdges.get(edge.to)!.push(edge);
    }

    this.graphs.set(sessionId, { nodes: allNodes, edges, outEdges, inEdges });
    onProgress?.(`[Graph] Knowledge graph ready — ${allNodes.size} nodes, ${edges.length} edges.`);
  }

  // ── Query methods ────────────────────────────────────────────────────────────

  // All files that import (transitively) the given file — impact radius
  getAffectedFiles(filePath: string, sessionId: string): string[] {
    const g = this.graphs.get(sessionId);
    if (!g) return [];
    const visited = new Set<string>();
    const queue = [filePath];
    while (queue.length && visited.size < 30) {
      const cur = queue.shift()!;
      if (visited.has(cur)) continue;
      visited.add(cur);
      (g.inEdges.get(cur) ?? []).filter(e => e.type === 'imports').forEach(e => queue.push(e.from));
    }
    return [...visited].filter(f => f !== filePath);
  }

  // All files this file depends on (transitive imports)
  getDependencies(filePath: string, sessionId: string): string[] {
    const g = this.graphs.get(sessionId);
    if (!g) return [];
    const visited = new Set<string>();
    const queue = [filePath];
    while (queue.length && visited.size < 30) {
      const cur = queue.shift()!;
      if (visited.has(cur)) continue;
      visited.add(cur);
      (g.outEdges.get(cur) ?? []).filter(e => e.type === 'imports').forEach(e => queue.push(e.to));
    }
    return [...visited].filter(f => f !== filePath);
  }

  // Find symbols and related files matching a natural-language query
  getContextForQuery(query: string, sessionId: string): { symbols: GNode[]; relatedFiles: string[] } {
    const g = this.graphs.get(sessionId);
    if (!g) return { symbols: [], relatedFiles: [] };

    const terms = query.toLowerCase().split(/\W+/).filter(t => t.length > 3);
    const matched: GNode[] = [];
    const relatedFiles = new Set<string>();

    for (const node of g.nodes.values()) {
      if (node.type === 'file') continue;
      const lower = node.name.toLowerCase();
      if (terms.some(t => lower.includes(t) || t.includes(lower))) {
        matched.push(node);
        relatedFiles.add(node.file);
        this.getAffectedFiles(node.file, sessionId).forEach(f => relatedFiles.add(f));
        this.getDependencies(node.file, sessionId).forEach(f => relatedFiles.add(f));
      }
    }

    return { symbols: matched.slice(0, 20), relatedFiles: [...relatedFiles].slice(0, 10) };
  }

  // Human-readable summary of a file's position in the graph
  getFileContext(filePath: string, sessionId: string): string {
    const g = this.graphs.get(sessionId);
    if (!g) return '';

    const lines: string[] = [`File: ${filePath}`];
    const symbols = [...g.nodes.values()].filter(n => n.file === filePath && n.type !== 'file');
    if (symbols.length) lines.push(`Exports: ${symbols.filter(s => s.exported).map(s => `${s.type} ${s.name}`).join(', ')}`);

    const deps = (g.outEdges.get(filePath) ?? []).filter(e => e.type === 'imports').map(e => e.to);
    if (deps.length) lines.push(`Imports: ${deps.join(', ')}`);

    const importedBy = (g.inEdges.get(filePath) ?? []).filter(e => e.type === 'imports').map(e => e.from);
    if (importedBy.length) lines.push(`Imported by: ${importedBy.join(', ')}`);

    const affected = this.getAffectedFiles(filePath, sessionId);
    if (affected.length) lines.push(`Change impact radius: ${affected.length} file(s) — ${affected.slice(0, 5).join(', ')}${affected.length > 5 ? '...' : ''}`);

    return lines.join('\n');
  }

  // Generate real import-dependency Mermaid diagram from graph edges
  toMermaid(sessionId: string, rootFiles?: string[]): string | null {
    const g = this.graphs.get(sessionId);
    if (!g) return null;

    const importEdges = g.edges.filter(e => e.type === 'imports');
    if (importEdges.length === 0) return null;

    let relevant: Set<string>;
    if (rootFiles?.length) {
      relevant = new Set(rootFiles);
      for (const f of rootFiles) {
        this.getDependencies(f, sessionId).forEach(d => relevant.add(d));
        this.getAffectedFiles(f, sessionId).forEach(a => relevant.add(a));
      }
    } else {
      // Pick the 25 most-connected files
      const connectivity = new Map<string, number>();
      for (const e of importEdges) {
        connectivity.set(e.from, (connectivity.get(e.from) ?? 0) + 1);
        connectivity.set(e.to, (connectivity.get(e.to) ?? 0) + 1);
      }
      relevant = new Set([...connectivity.entries()].sort((a, b) => b[1] - a[1]).slice(0, 25).map(([f]) => f));
    }

    const sanitize = (s: string) => s.replace(/[^a-zA-Z0-9]/g, '_').replace(/^_+/, 'f');
    const lines = ['graph LR'];

    for (const f of relevant) {
      lines.push(`  ${sanitize(f)}["${path.basename(f)}"]`);
    }

    const seen = new Set<string>();
    for (const e of importEdges) {
      if (!relevant.has(e.from) || !relevant.has(e.to)) continue;
      const key = `${e.from}→${e.to}`;
      if (!seen.has(key)) {
        seen.add(key);
        lines.push(`  ${sanitize(e.from)} --> ${sanitize(e.to)}`);
      }
    }

    return lines.length > relevant.size + 1 ? lines.join('\n') : null;
  }

  // Generate a class hierarchy Mermaid diagram
  toClassDiagram(sessionId: string, fileFilter?: string[]): string | null {
    const g = this.graphs.get(sessionId);
    if (!g) return null;

    const classes = [...g.nodes.values()].filter(n =>
      n.type === 'class' && (!fileFilter?.length || fileFilter.some(f => n.file.includes(f)))
    );
    if (classes.length === 0) return null;

    const lines = ['classDiagram'];
    for (const cls of classes.slice(0, 20)) {
      const methods = [...g.nodes.values()].filter(n => n.file === cls.file && n.type === 'function' && n.exported);
      lines.push(`  class ${cls.name} {`);
      for (const m of methods.slice(0, 6)) lines.push(`    +${m.name}()`);
      lines.push('  }');
    }

    for (const e of g.edges.filter(e2 => e2.type === 'extends')) {
      const from = g.nodes.get(e.from);
      const to = g.nodes.get(e.to);
      if (from && to) lines.push(`  ${to.name} <|-- ${from.name}`);
    }

    return lines.length > 1 ? lines.join('\n') : null;
  }

  // Compact text summary of the whole graph — used in prompts
  getSummary(sessionId: string): string {
    const g = this.graphs.get(sessionId);
    if (!g) return '';

    const fileCount = [...g.nodes.values()].filter(n => n.type === 'file').length;
    const symbolCount = [...g.nodes.values()].filter(n => n.type !== 'file').length;
    const importCount = g.edges.filter(e => e.type === 'imports').length;

    const topFiles = [...g.nodes.values()]
      .filter(n => n.type === 'file')
      .map(n => ({
        file: n.file,
        inDegree: (g.inEdges.get(n.file) ?? []).filter(e => e.type === 'imports').length,
      }))
      .sort((a, b) => b.inDegree - a.inDegree)
      .slice(0, 8)
      .map(x => `${x.file} (imported by ${x.inDegree})`)
      .join(', ');

    return `Knowledge graph: ${fileCount} files, ${symbolCount} symbols, ${importCount} import edges.\nMost-imported files: ${topFiles}`;
  }

  private getCodeFiles(dir: string): string[] {
    const results: string[] = [];
    const walk = (d: string) => {
      try {
        for (const entry of fs.readdirSync(d)) {
          if (SKIP_DIRS.has(entry)) continue;
          const full = path.join(d, entry);
          if (fs.statSync(full).isDirectory()) walk(full);
          else if (CODE_EXTS.has(path.extname(entry))) results.push(full);
        }
      } catch { /* ignore */ }
    };
    walk(dir);
    return results;
  }
}

export const graphIndexer = new GraphIndexer();
