import path from 'path';
import { GraphEdge } from '../types/project_graph.ts';

interface FileEntry {
  relativePath: string;
  content: string;
  language: string;
}

const IMPORT_PATTERNS: Record<string, RegExp[]> = {
  typescript: [
    /import\s+.*?\s+from\s+['"]([^'"]+)['"]/g,
    /import\s+['"]([^'"]+)['"]/g,
    /require\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
    /export\s+.*?\s+from\s+['"]([^'"]+)['"]/g,
  ],
  javascript: [
    /import\s+.*?\s+from\s+['"]([^'"]+)['"]/g,
    /import\s+['"]([^'"]+)['"]/g,
    /require\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
    /export\s+.*?\s+from\s+['"]([^'"]+)['"]/g,
  ],
  python: [
    /^from\s+([\w.]+)\s+import/gm,
    /^import\s+([\w.]+)/gm,
  ],
  go: [
    /["']([\w./]+)["']/g,
  ],
};

function makeNodeId(relativePath: string): string {
  return relativePath.replace(/\\/g, '/');
}

function resolveImport(importPath: string, fromFile: string, allPaths: Set<string>): string | null {
  if (!importPath.startsWith('.')) return null;

  const fromDir = path.dirname(fromFile);
  const resolved = path.normalize(path.join(fromDir, importPath)).replace(/\\/g, '/');

  // Try exact match
  if (allPaths.has(resolved)) return resolved;

  // Try with common extensions
  for (const ext of ['.ts', '.tsx', '.js', '.jsx', '.py', '.go']) {
    const withExt = resolved + ext;
    if (allPaths.has(withExt)) return withExt;
  }

  // Try index files
  for (const idx of ['index.ts', 'index.tsx', 'index.js', 'index.jsx']) {
    const withIndex = resolved + '/' + idx;
    if (allPaths.has(withIndex)) return withIndex;
  }

  return null;
}

export function analyzeDependencies(files: FileEntry[]): GraphEdge[] {
  const allPaths = new Set(files.map(f => makeNodeId(f.relativePath)));
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();

  for (const file of files) {
    const patterns = IMPORT_PATTERNS[file.language] ?? [];
    const sourceId = makeNodeId(file.relativePath);

    for (const pattern of patterns) {
      pattern.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = pattern.exec(file.content)) !== null) {
        const importPath = match[1];
        if (!importPath) continue;

        const targetRelative = resolveImport(importPath, file.relativePath, allPaths);
        if (!targetRelative) continue;

        const targetId = makeNodeId(targetRelative);
        const edgeId = `${sourceId}->${targetId}:imports`;
        if (seen.has(edgeId)) continue;
        seen.add(edgeId);

        edges.push({
          id: edgeId,
          source: sourceId,
          target: targetId,
          kind: 'imports',
          label: path.basename(importPath),
        });
      }
    }
  }

  return edges;
}
