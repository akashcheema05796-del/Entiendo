import { GraphEdge } from './project_graph.ts';

export type CodingTask = 'explain' | 'diagram' | 'refactor' | 'add_feature' | 'fix_bug' | 'generate_tests';
export type CodingIntent = 'explain' | 'diagram' | 'refactor' | 'error';

export interface SelectionContext {
  sessionId: string;
  selectedNodeIds: string[];
  selectionKind: 'node' | 'directory' | 'freehand';
  resolvedFiles: string[];      // absolute paths
  resolvedEdges: GraphEdge[];   // edges between selected nodes
  contentRef: string | null;    // store.put(Map<relativePath, content>)
}
