import { Annotation } from '@langchain/langgraph';
import { CodingTask } from '../types/selection_context.ts';

export const CodingAgentStateAnnotation = Annotation.Root({
  sessionId: Annotation<string>(),
  userQuery: Annotation<string>(),
  repoPath: Annotation<string>(),
  task: Annotation<CodingTask>(),

  // Refs into session_store — no raw code or large objects in state
  selectionRef: Annotation<string | null>(),
  llmConfigRef: Annotation<string | null>(),
  graphRef: Annotation<string | null>(),

  // Output
  outputType: Annotation<'markdown' | 'mermaid' | 'diff_proposal' | null>(),
  outputRef: Annotation<string | null>(),
  pendingDiffId: Annotation<string | null>(),
  error: Annotation<string | null>(),
});

export type CodingAgentState = typeof CodingAgentStateAnnotation.State;
