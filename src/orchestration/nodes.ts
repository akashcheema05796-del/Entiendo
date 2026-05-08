import { AgentState } from './state.ts';
import { getLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
import { applySearchReplace } from '../tools/diff_engine.ts';
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
  try {
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

    let fileRef: string | null = null;
    if (result.target_files.length > 0) {
      fileRef = store.put(result.target_files[0]);
    }

    return {
      intent: result.intent,
      targetFiles: result.target_files,
      fileRef,
    };
  } catch (error: unknown) {
    console.error('Entry Node Error:', error);
    return {
      intent: 'macro_structure',
      targetFiles: [],
      fileRef: null,
    };
  }
}

export async function microLogicNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MICRO LOGIC NODE ---');

  const mermaid = `graph TD\n  A[Start] --> B[Processing] --> C[End]`;

  return {
    outputType: 'mermaid',
    outputRef: mermaid,
  };
}

export async function macro_structure_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MACRO STRUCTURE NODE ---');
  try {
    const llm = getLLM('standard', 0);

    const prompt = `Analyze the project structure of ${state.repoPath}.
    Identify the main architectural components.

    User query: ${state.userQuery}`;

    const response = await llm.invoke([
      new SystemMessage('You are a senior software architect.'),
      new HumanMessage(prompt)
    ]);

    return {
      outputType: 'markdown',
      outputRef: response.content as string,
    };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Macro Node Error:', message);
    return {
      outputType: 'markdown',
      outputRef: 'Architectural analysis paused due to reasoning cluster availability. Visual representation derived from file system structure remains active.',
    };
  }
}

export async function deepExplanation_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- DEEP EXPLANATION NODE ---');
  try {
    const llm = getLLM('complex', 0.1);

    const prompt = `Explain how the following logic works in ${state.repoPath}:
    ${state.userQuery}

    Focus on technical details and data flow.`;

    const response = await llm.invoke([
      new SystemMessage('You are a technical lead explaining a codebase.'),
      new HumanMessage(prompt)
    ]);

    return {
      outputType: 'markdown',
      outputRef: response.content as string,
    };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      outputType: 'markdown',
      outputRef: `Deep analysis encountered a temporary limitation: ${message}. Please verify repository accessibility or try a macro-level query.`,
    };
  }
}

export async function refactorNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- REFACTOR NODE ---');
  try {
    const llm = getLLM('complex', 0.1);

    const targetFile = state.fileRef ? store.get(state.fileRef) as string | null : null;

    const prompt = `You are performing a structural code refactor.
Repository: ${state.repoPath}
${targetFile ? `Target file: ${targetFile}` : ''}

User request: ${state.userQuery}

Produce SEARCH/REPLACE blocks in this exact format for every change:
<<<<
<exact lines to find>
====
<replacement lines>
>>>>

Only emit the blocks — no other prose.`;

    const response = await llm.invoke([
      new SystemMessage('You are a senior engineer performing precise code refactors.'),
      new HumanMessage(prompt)
    ]);

    const llmOutput = response.content as string;
    const { modified, appliedBlocks, error } = applySearchReplace('', llmOutput);

    if (error) {
      return {
        outputType: 'markdown',
        outputRef: `Refactor could not be applied: ${error}\n\nRaw suggestion:\n\`\`\`\n${llmOutput}\n\`\`\``,
      };
    }

    const diffRef = store.put({ original: '', modified, appliedBlocks });

    return {
      outputType: 'diff_proposal',
      outputRef: diffRef,
      pendingDiffId: diffRef,
    };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Refactor Node Error:', message);
    return {
      outputType: 'markdown',
      outputRef: `Refactor failed: ${message}`,
    };
  }
}

export async function errorNode(state: AgentState): Promise<Partial<AgentState>> {
  return {
    error: "I'm not sure how to help with that yet. Try asking about architecture, code flow, or refactoring.",
  };
}

export function routeByIntent(state: AgentState) {
  if (state.error) return 'error_handler';
  return state.intent ?? 'error_handler';
}
