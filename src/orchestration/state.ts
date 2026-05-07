import { Annotation } from '@langchain/langgraph';

/**
 * state.ts
 * Pointer-Based AgentState. No raw code in state.
 */
export const AgentStateAnnotation = Annotation.Root({
  // Connection context
  sessionId: Annotation<string>(),
  
  // Input
  userQuery: Annotation<string>(),
  repoPath: Annotation<string>(),
  
  // Router output
  intent: Annotation<'macro_structure' | 'micro_logic' | 'deep_explanation' | 'refactor' | 'error'>(),
  targetFiles: Annotation<string[]>(),
  
  // Pointers to SessionStore — never raw code in state
  fileRef: Annotation<string | null>(),
  retrievedChunkIds: Annotation<string[]>(),
  pendingDiffId: Annotation<string | null>(),
  
  // Output metadata
  outputType: Annotation<'svg_path' | 'mermaid' | 'markdown' | 'diff_proposal' | null>(),
  outputRef: Annotation<string | null>(),
  
  // Error handling
  error: Annotation<string | null>(),
});

export type AgentState = typeof AgentStateAnnotation.State;
