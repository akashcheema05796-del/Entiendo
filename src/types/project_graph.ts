export type NodeKind = 'file' | 'directory' | 'function' | 'class' | 'interface' | 'variable';
export type EdgeKind = 'imports' | 'calls' | 'inherits' | 'implements' | 'uses_type' | 'contains';

export interface SymbolRef {
  name: string;
  kind: 'function' | 'class' | 'interface' | 'type' | 'const';
  startLine: number;
  endLine: number;
}

export interface GraphNode {
  id: string;           // sha1-like: relativePath:symbolName or just relativePath
  kind: NodeKind;
  label: string;        // short display name
  relativePath: string;
  language: string;
  loc: number;
  symbols: SymbolRef[];
  x?: number;
  y?: number;
}

export interface GraphEdge {
  id: string;           // source->target:kind
  source: string;       // GraphNode.id
  target: string;       // GraphNode.id
  kind: EdgeKind;
  label?: string;
}

export interface ProjectGraph {
  workspacePath: string;
  generatedAt: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}
