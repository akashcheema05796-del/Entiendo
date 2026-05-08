import { SymbolRef, GraphEdge } from '../types/project_graph.ts';

interface SymbolPattern {
  kind: SymbolRef['kind'];
  pattern: RegExp;
  nameGroup: number;
}

const PATTERNS: Record<string, SymbolPattern[]> = {
  typescript: [
    { kind: 'function',  pattern: /^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[(<]/gm,  nameGroup: 1 },
    { kind: 'class',     pattern: /^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/gm,          nameGroup: 1 },
    { kind: 'interface', pattern: /^(?:export\s+)?interface\s+(\w+)/gm,                      nameGroup: 1 },
    { kind: 'type',      pattern: /^(?:export\s+)?type\s+(\w+)\s*=/gm,                       nameGroup: 1 },
    { kind: 'const',     pattern: /^(?:export\s+)?const\s+(\w+)\s*[=:]/gm,                  nameGroup: 1 },
    { kind: 'function',  pattern: /^(?:export\s+)?(?:const\s+)(\w+)\s*=\s*(?:async\s*)?\(/gm, nameGroup: 1 },
  ],
  javascript: [
    { kind: 'function',  pattern: /^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(/gm,    nameGroup: 1 },
    { kind: 'class',     pattern: /^(?:export\s+)?class\s+(\w+)/gm,                          nameGroup: 1 },
    { kind: 'const',     pattern: /^(?:export\s+)?const\s+(\w+)\s*=/gm,                     nameGroup: 1 },
  ],
  python: [
    { kind: 'function',  pattern: /^(?:async\s+)?def\s+(\w+)\s*\(/gm,                       nameGroup: 1 },
    { kind: 'class',     pattern: /^class\s+(\w+)/gm,                                        nameGroup: 1 },
  ],
  go: [
    { kind: 'function',  pattern: /^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(/gm,                  nameGroup: 1 },
    { kind: 'type',      pattern: /^type\s+(\w+)\s+struct/gm,                                nameGroup: 1 },
    { kind: 'interface', pattern: /^type\s+(\w+)\s+interface/gm,                             nameGroup: 1 },
  ],
};

export function extractSymbols(relativePath: string, content: string, language: string): SymbolRef[] {
  const patterns = PATTERNS[language] ?? [];
  const lines = content.split('\n');
  const symbols: SymbolRef[] = [];

  for (const { kind, pattern, nameGroup } of patterns) {
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(content)) !== null) {
      const name = match[nameGroup];
      if (!name || name.startsWith('_') && name.length === 1) continue;

      // Find line number from match index
      const beforeMatch = content.slice(0, match.index);
      const startLine = beforeMatch.split('\n').length;

      // Estimate end line (find next top-level definition or +20 lines)
      const endLine = Math.min(startLine + 20, lines.length);

      symbols.push({ name, kind, startLine, endLine });
    }
  }

  return symbols;
}

// Extract call relationships between symbols in the same file
export function extractCallEdges(
  relativePath: string,
  symbols: SymbolRef[],
  content: string
): GraphEdge[] {
  const edges: GraphEdge[] = [];
  const lines = content.split('\n');

  for (const caller of symbols) {
    if (caller.kind !== 'function' && caller.kind !== 'class') continue;
    const body = lines.slice(caller.startLine, caller.endLine).join('\n');

    for (const callee of symbols) {
      if (callee.name === caller.name) continue;
      // Check if callee name appears in caller body
      const callPattern = new RegExp(`\\b${callee.name}\\s*[.(]`);
      if (callPattern.test(body)) {
        const edgeId = `${relativePath}:${caller.name}->${callee.name}:calls`;
        edges.push({
          id: edgeId,
          source: `${relativePath}:${caller.name}`,
          target: `${relativePath}:${callee.name}`,
          kind: 'calls',
        });
      }
    }
  }

  return edges;
}
