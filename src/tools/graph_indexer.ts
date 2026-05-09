import fs from 'fs';
import path from 'path';

const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.next', 'build', 'coverage']);
const CODE_EXTS = new Set(['.ts', '.tsx', '.js', '.jsx', '.py']);

// ── Types ──────────────────────────────────────────────────────────────────────

export type NodeType = 'file' | 'function' | 'method' | 'class' | 'interface' | 'type' | 'enum' | 'const';
export type EdgeType = 'imports' | 'defines' | 'contains' | 'extends' | 'implements';

export interface GNode {
  id: string;
  type: NodeType;
  file: string;          // relative path from repo root
  name: string;
  line: number;          // 1-based line number
  exported: boolean;
  parent?: string;       // id of the containing class node (for method nodes)
  signature?: string;    // parameter list, e.g. "(name: string, age: number)"
  visibility?: 'public' | 'private' | 'protected';
  abstract?: boolean;
  static?: boolean;
  async?: boolean;
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
  return null; // don't create phantom graph nodes for unresolvable paths
}

// ── TS/JS parser ───────────────────────────────────────────────────────────────

function parseJSTS(content: string, relPath: string, repoPath: string): { nodes: GNode[]; edges: GEdge[] } {
  const fileId = relPath;
  const nodes: GNode[] = [{ id: fileId, type: 'file', file: relPath, name: path.basename(relPath), line: 1, exported: true }];
  const edges: GEdge[] = [];

  const lines = content.split('\n');

  // Brace-depth tracking for class scope
  let braceDepth = 0;
  interface PendingClass { id: string; depth: number }
  const classStack: PendingClass[] = [];

  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1;
    const raw = lines[i];
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

    // ── Class definitions ─────────────────────────────────────────────────────
    const classMatch = line.match(/^(export\s+(?:default\s+)?)?(?:(abstract)\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?/);
    if (classMatch) {
      const isExported = !!(classMatch[1]);
      const isAbstract = !!(classMatch[2]);
      const name = classMatch[3];
      const parentName = classMatch[4];
      const implementsList = classMatch[5];
      const symId = `${fileId}::${name}`;

      if (!nodes.find(n => n.id === symId)) {
        nodes.push({
          id: symId, type: 'class', file: relPath, name,
          line: lineNum, exported: isExported, abstract: isAbstract,
        });
        edges.push({ from: fileId, to: symId, type: 'defines' });

        if (parentName) {
          edges.push({ from: symId, to: `__unresolved__::${parentName}`, type: 'extends' });
        }
        if (implementsList) {
          for (const iface of implementsList.split(',').map(s => s.trim()).filter(Boolean)) {
            edges.push({ from: symId, to: `__unresolved__::${iface}`, type: 'implements' });
          }
        }
      }

      // Track the brace depth when this class opens so we can scope its methods
      const openBraces = (raw.match(/\{/g) ?? []).length;
      const closeBraces = (raw.match(/\}/g) ?? []).length;
      const netOpen = openBraces - closeBraces;
      // Push class onto stack; its methods live at depth braceDepth+1 after this line
      classStack.push({ id: symId, depth: braceDepth + (netOpen > 0 ? 1 : 0) });
      braceDepth += netOpen;
      continue;
    }

    // ── Interface definitions ─────────────────────────────────────────────────
    const ifaceMatch = line.match(/^(export\s+)?interface\s+(\w+)(?:\s+extends\s+([\w,\s]+))?/);
    if (ifaceMatch) {
      const isExported = !!(ifaceMatch[1]);
      const name = ifaceMatch[2];
      const extendsList = ifaceMatch[3];
      const symId = `${fileId}::${name}`;

      if (!nodes.find(n => n.id === symId)) {
        nodes.push({ id: symId, type: 'interface', file: relPath, name, line: lineNum, exported: isExported });
        edges.push({ from: fileId, to: symId, type: 'defines' });

        if (extendsList) {
          for (const base of extendsList.split(',').map(s => s.trim()).filter(Boolean)) {
            edges.push({ from: symId, to: `__unresolved__::${base}`, type: 'extends' });
          }
        }
      }
    }

    // ── Type alias definitions ────────────────────────────────────────────────
    const typeMatch = line.match(/^(export\s+)?type\s+(\w+)\s*(?:<[^>]*>)?\s*=/);
    if (typeMatch) {
      const isExported = !!(typeMatch[1]);
      const name = typeMatch[2];
      const symId = `${fileId}::${name}`;
      if (!nodes.find(n => n.id === symId)) {
        nodes.push({ id: symId, type: 'type', file: relPath, name, line: lineNum, exported: isExported });
        edges.push({ from: fileId, to: symId, type: 'defines' });
      }
    }

    // ── Enum definitions ──────────────────────────────────────────────────────
    const enumMatch = line.match(/^(export\s+)?(?:const\s+)?enum\s+(\w+)/);
    if (enumMatch) {
      const isExported = !!(enumMatch[1]);
      const name = enumMatch[2];
      const symId = `${fileId}::${name}`;
      if (!nodes.find(n => n.id === symId)) {
        nodes.push({ id: symId, type: 'enum', file: relPath, name, line: lineNum, exported: isExported });
        edges.push({ from: fileId, to: symId, type: 'defines' });
      }
    }

    // ── Function / method definitions ─────────────────────────────────────────
    // Determine active class scope from brace depth
    const currentClass = classStack.length > 0 ? classStack[classStack.length - 1] : null;
    const insideClass = currentClass !== null && braceDepth > currentClass.depth;

    if (insideClass) {
      // Inside a class body: detect methods
      const visibilityPrefix = /^(public|private|protected)\s+/.exec(line);
      const vis = visibilityPrefix ? (visibilityPrefix[1] as 'public' | 'private' | 'protected') : 'public';
      const strippedLine = visibilityPrefix ? line.slice(visibilityPrefix[0].length) : line;

      const isStatic = /^static\s+/.test(strippedLine);
      const afterStatic = isStatic ? strippedLine.replace(/^static\s+/, '') : strippedLine;
      const isAsync = /^async\s+/.test(afterStatic);
      const afterAsync = isAsync ? afterStatic.replace(/^async\s+/, '') : afterStatic;
      const isAbstractMethod = /^abstract\s+/.test(afterAsync);
      const afterAbstract = isAbstractMethod ? afterAsync.replace(/^abstract\s+/, '') : afterAsync;

      // Method: name(...) or name = (...) =>
      const methodMatch =
        afterAbstract.match(/^(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)/) ||
        afterAbstract.match(/^(\w+)\s*=\s*(?:async\s+)?\(/);

      if (methodMatch) {
        const name = methodMatch[1];
        const sig = methodMatch[2] !== undefined ? `(${methodMatch[2]})` : '(...)';
        // Skip keywords that look like method calls
        if (name && /^[a-zA-Z_$]/.test(name) && !['if', 'for', 'while', 'switch', 'catch'].includes(name)) {
          const classNode = currentClass.id;
          const symId = `${classNode}::${name}`;
          if (!nodes.find(n => n.id === symId)) {
            nodes.push({
              id: symId, type: 'method', file: relPath, name,
              line: lineNum, exported: vis === 'public',
              parent: classNode, signature: sig,
              visibility: vis, static: isStatic, async: isAsync, abstract: isAbstractMethod,
            });
            edges.push({ from: classNode, to: symId, type: 'contains' });
          }
        }
      }
    } else {
      // Top-level or outside class body: detect functions and const arrow fns
      const fnMatch =
        line.match(/^(export\s+(?:default\s+)?)?(async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)/) ||
        line.match(/^(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?\(([^)]*)/) ||
        line.match(/^(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?function\s*\(([^)]*)/);

      if (fnMatch) {
        const isExported = !!(fnMatch[1]);
        const isAsync = !!(fnMatch[2] || fnMatch[3]);
        const name = fnMatch[3] ?? fnMatch[2];
        const sigParams = fnMatch[4] ?? '';

        if (name && /^[A-Za-z_$]/.test(name)) {
          const symId = `${fileId}::${name}`;
          if (!nodes.find(n => n.id === symId)) {
            nodes.push({
              id: symId, type: 'function', file: relPath, name,
              line: lineNum, exported: isExported, async: isAsync,
              signature: `(${sigParams.split('\n')[0].trim()})`,
            });
            edges.push({ from: fileId, to: symId, type: 'defines' });
          }
        }
      }

      // Top-level const (non-function)
      const constMatch = line.match(/^(export\s+)?const\s+(\w+)\s*(?::\s*[\w<>[\]|&]+)?\s*=(?!\s*(?:async\s+)?\(|(?:async\s+)?function)/);
      if (constMatch) {
        const isExported = !!(constMatch[1]);
        const name = constMatch[2];
        if (name && /^[A-Z]/.test(name[0])) { // only capitalised consts (likely important exports)
          const symId = `${fileId}::${name}`;
          if (!nodes.find(n => n.id === symId)) {
            nodes.push({ id: symId, type: 'const', file: relPath, name, line: lineNum, exported: isExported });
            edges.push({ from: fileId, to: symId, type: 'defines' });
          }
        }
      }
    }

    // ── Update brace depth (must be last in loop) ─────────────────────────────
    // Skip lines that were class declarations (already processed above)
    if (!classMatch) {
      const openBraces = (raw.match(/\{/g) ?? []).length;
      const closeBraces = (raw.match(/\}/g) ?? []).length;
      braceDepth += openBraces - closeBraces;
    }

    // Pop finished classes off the stack
    while (classStack.length > 0 && braceDepth <= classStack[classStack.length - 1].depth) {
      classStack.pop();
    }
  }

  return { nodes, edges };
}

// ── Python parser ──────────────────────────────────────────────────────────────

function parsePython(content: string, relPath: string, repoPath: string): { nodes: GNode[]; edges: GEdge[] } {
  const fileId = relPath;
  const nodes: GNode[] = [{ id: fileId, type: 'file', file: relPath, name: path.basename(relPath), line: 1, exported: true }];
  const edges: GEdge[] = [];

  const lines = content.split('\n');

  // Track the current class by indent level
  interface PyClass { id: string; indent: number }
  const classStack: PyClass[] = [];

  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1;
    const raw = lines[i];
    const indent = raw.match(/^(\s*)/)?.[1].length ?? 0;
    const line = raw.trim();

    // Pop classes whose indent is no longer deeper than current line
    while (classStack.length > 0 && indent <= classStack[classStack.length - 1].indent) {
      classStack.pop();
    }

    const fromImport = line.match(/^from\s+(\S+)\s+import/);
    if (fromImport) {
      const mod = fromImport[1].replace(/\./g, '/');
      const resolved = resolveImport(relPath, `./${mod}`, repoPath);
      if (resolved) edges.push({ from: fileId, to: resolved, type: 'imports' });
      continue;
    }

    const plainImport = line.match(/^import\s+([\w.]+)/);
    if (plainImport) continue; // external or stdlib, skip

    // Class definition
    const classMatch = line.match(/^class\s+(\w+)(?:\(([^)]*)\))?/);
    if (classMatch) {
      const name = classMatch[1];
      const bases = classMatch[2];
      const symId = `${fileId}::${name}`;
      if (!nodes.find(n => n.id === symId)) {
        nodes.push({ id: symId, type: 'class', file: relPath, name, line: lineNum, exported: !name.startsWith('_') });
        edges.push({ from: fileId, to: symId, type: 'defines' });
        if (bases) {
          for (const base of bases.split(',').map(s => s.trim()).filter(Boolean)) {
            if (base !== 'object') {
              edges.push({ from: symId, to: `__unresolved__::${base}`, type: 'extends' });
            }
          }
        }
      }
      classStack.push({ id: symId, indent });
      continue;
    }

    // Function / method definition
    const fnMatch = line.match(/^(?:(async)\s+)?def\s+(\w+)\s*\(([^)]*)\)/);
    if (fnMatch) {
      const isAsync = !!(fnMatch[1]);
      const name = fnMatch[2];
      const sig = `(${fnMatch[3]})`;
      const currentClass = classStack.length > 0 ? classStack[classStack.length - 1] : null;

      if (currentClass) {
        // Method inside a class
        const vis: 'public' | 'private' | 'protected' = name.startsWith('__') && !name.endsWith('__') ? 'private'
          : name.startsWith('_') ? 'protected' : 'public';
        const symId = `${currentClass.id}::${name}`;
        if (!nodes.find(n => n.id === symId)) {
          nodes.push({
            id: symId, type: 'method', file: relPath, name,
            line: lineNum, exported: vis === 'public',
            parent: currentClass.id, signature: sig,
            visibility: vis, async: isAsync,
          });
          edges.push({ from: currentClass.id, to: symId, type: 'contains' });
        }
      } else {
        // Module-level function
        const symId = `${fileId}::${name}`;
        if (!nodes.find(n => n.id === symId)) {
          nodes.push({
            id: symId, type: 'function', file: relPath, name,
            line: lineNum, exported: !name.startsWith('_'),
            signature: sig, async: isAsync,
          });
          edges.push({ from: fileId, to: symId, type: 'defines' });
        }
      }
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

    // Resolve __unresolved__ extends/implements edges against the global symbol table
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

    // Only keep terms longer than 3 chars to avoid noise; match only node-name-contains-term
    const terms = query.toLowerCase().split(/\W+/).filter(t => t.length > 3);
    const matched: GNode[] = [];
    const relatedFiles = new Set<string>();

    for (const node of g.nodes.values()) {
      if (node.type === 'file') continue;
      const lower = node.name.toLowerCase();
      if (terms.some(t => lower.includes(t))) {
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

    // Top-level exported symbols
    const topLevel = [...g.nodes.values()].filter(n =>
      n.file === filePath && n.type !== 'file' && !n.parent && n.exported
    );
    if (topLevel.length) {
      lines.push(`Exports: ${topLevel.map(s => {
        const vis = s.visibility && s.visibility !== 'public' ? `${s.visibility} ` : '';
        const mod = [s.static ? 'static' : '', s.async ? 'async' : '', s.abstract ? 'abstract' : ''].filter(Boolean).join(' ');
        const modStr = mod ? `[${mod}] ` : '';
        return `${modStr}${vis}${s.type} ${s.name}${s.signature ?? ''}:${s.line}`;
      }).join(', ')}`);
    }

    // Classes with their method counts
    const classes = [...g.nodes.values()].filter(n => n.file === filePath && n.type === 'class');
    for (const cls of classes) {
      const methods = (g.outEdges.get(cls.id) ?? [])
        .filter(e => e.type === 'contains')
        .map(e => g.nodes.get(e.to))
        .filter((n): n is GNode => n !== undefined);
      if (methods.length) {
        lines.push(`  ${cls.name}: ${methods.map(m => `${m.visibility === 'private' ? '-' : m.visibility === 'protected' ? '#' : '+'}${m.name}${m.signature ?? '()'}`).join(', ')}`);
      }
    }

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

  // Generate a class hierarchy Mermaid diagram using `contains` edges for methods
  toClassDiagram(sessionId: string, fileFilter?: string[]): string | null {
    const g = this.graphs.get(sessionId);
    if (!g) return null;

    const classes = [...g.nodes.values()].filter(n =>
      n.type === 'class' && (!fileFilter?.length || fileFilter.some(f => n.file.includes(f)))
    );
    if (classes.length === 0) return null;

    const lines = ['classDiagram'];
    for (const cls of classes.slice(0, 20)) {
      // Get methods via `contains` edges — only real class members
      const methods = (g.outEdges.get(cls.id) ?? [])
        .filter(e => e.type === 'contains')
        .map(e => g.nodes.get(e.to))
        .filter((n): n is GNode => n !== undefined && n.type === 'method');

      lines.push(`  class ${cls.name} {`);
      if (cls.abstract) lines.push(`    <<abstract>>`);
      for (const m of methods.slice(0, 8)) {
        const prefix = m.visibility === 'private' ? '-' : m.visibility === 'protected' ? '#' : '+';
        const mods = [m.static ? '$' : '', m.abstract ? '*' : ''].filter(Boolean).join('');
        lines.push(`    ${prefix}${m.name}()${mods}`);
      }
      lines.push('  }');
    }

    for (const e of g.edges) {
      if (e.type !== 'extends' && e.type !== 'implements') continue;
      const from = g.nodes.get(e.from);
      const to = g.nodes.get(e.to);
      if (!from || !to) continue;
      if (e.type === 'extends') lines.push(`  ${to.name} <|-- ${from.name}`);
      if (e.type === 'implements') lines.push(`  ${to.name} <|.. ${from.name}`);
    }

    return lines.length > 1 ? lines.join('\n') : null;
  }

  // Compact text summary of the whole graph — used in prompts
  getSummary(sessionId: string): string {
    const g = this.graphs.get(sessionId);
    if (!g) return '';

    const nodes = [...g.nodes.values()];
    const fileCount = nodes.filter(n => n.type === 'file').length;
    const classCount = nodes.filter(n => n.type === 'class').length;
    const methodCount = nodes.filter(n => n.type === 'method').length;
    const fnCount = nodes.filter(n => n.type === 'function').length;
    const importCount = g.edges.filter(e => e.type === 'imports').length;

    const topFiles = nodes
      .filter(n => n.type === 'file')
      .map(n => ({
        file: n.file,
        inDegree: (g.inEdges.get(n.file) ?? []).filter(e => e.type === 'imports').length,
      }))
      .sort((a, b) => b.inDegree - a.inDegree)
      .slice(0, 8)
      .map(x => `${x.file} (imported by ${x.inDegree})`)
      .join(', ');

    return [
      `Knowledge graph: ${fileCount} files, ${classCount} classes, ${methodCount} methods, ${fnCount} functions, ${importCount} import edges.`,
      `Most-imported files: ${topFiles}`,
    ].join('\n');
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
