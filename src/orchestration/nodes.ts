import { AgentState } from './state.ts';
import { getLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
import { z } from 'zod';
import { SystemMessage, HumanMessage } from '@langchain/core/messages';

/**
 * nodes.ts
 * Implementation of the LangGraph nodes.
 */

const RouterSchema = z.object({
  intent: z.enum(['macro_structure', 'micro_logic', 'deep_explanation', 'refactor', 'error']),
  target_files: z.array(z.string()),
  confidence: z.number(),
});

export async function entryNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- ENTRY NODE ---');
  const llm = getLLM('standard', 0);
  const structuredLlm = llm.withStructuredOutput(RouterSchema);

  const prompt = `Classify user intent for codebase analysis.
  - macro_structure: Visualization, dependency graphs, architectural overview.
  - micro_logic: UML, flowcharts, logic within a single file.
  - deep_explanation: RAG-based search, "how does X work?".
  - refactor: Editing code, fixing bugs, optimization.
  
  User query: ${state.userQuery}`;

  const result = await structuredLlm.invoke([
    new SystemMessage('You are a senior codebase architect router.'),
    new HumanMessage(prompt)
  ]) as z.infer<typeof RouterSchema>;

  let fileRef = null;
  if (result.target_files.length > 0) {
    fileRef = store.put(result.target_files[0]); // Pointer to the target file if found
  }

  return {
    intent: result.intent,
    targetFiles: result.target_files,
    fileRef: fileRef,
  };
}

export async function microLogicNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MICRO LOGIC NODE ---');
  // In a real scenario, we'd read the file content using the fileRef
  // and generate a Mermaid diagram.
  
  const mermaid = `graph TD\n  A[Start] --> B[Processing] --> C[End]`;
  const outputRef = store.put(mermaid);

  return {
    outputType: 'mermaid',
    outputRef: outputRef,
  };
}

export async function errorNode(state: AgentState): Promise<Partial<AgentState>> {
  return {
    error: 'I am not sure how to help with that yet. Try asking about architecture or refactoring.',
  };
}

export function routeByIntent(state: AgentState) {
  if (state.error) return 'error';
  return state.intent || 'error';
}
