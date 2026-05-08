import fs from 'fs';
import path from 'path';
import { AgentState } from './state.ts';
import { getLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
import { applySearchReplace } from '../tools/diff_engine.ts';
import { ragIndexer } from '../tools/rag_indexer.ts';
import { z } from 'zod';
import { SystemMessage, HumanMessage } from '@langchain/core/messages';
import { tokenEmitter } from '../infrastructure/token_emitter.ts';

/**
 * nodes.ts
 * Implementation of the LangGraph nodes.
 */

const RouterSchema = z.object({
  intent: z.enum(['macro_structure', 'micro_logic', 'diagram', 'deep_explanation', 'refactor', 'error']),
  target_files: z.array(z.string()),
  confidence: z.number(),
});

export async function entryNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- ENTRY NODE ---');
  try {
    const llm = getLLM('standard', 0);
    const structuredLlm = llm.withStructuredOutput(RouterSchema);

    const prompt = `Classify user intent for codebase analysis.
    - macro_structure: High-level architectural overview, project structure summary.
    - micro_logic: UML, sequence diagrams, logic within a single file.
    - diagram: Explicit request for a Mermaid diagram — flowcharts, dependency graphs, class/entity diagrams, system maps.
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
  try {
    const llm = getLLM('standard', 0);

    const targetFileName = state.fileRef ? (store.get(state.fileRef) as string | null) : null;
    const targetFilePath = targetFileName && state.repoPath ? path.join(state.repoPath, targetFileName) : null;

    let fileContent = '';
    if (targetFilePath) {
      try { fileContent = fs.readFileSync(targetFilePath, 'utf-8'); } catch { /* not found */ }
    }

    const prompt = `Generate a Mermaid diagram for the logic or flow described below.
Repository: ${state.repoPath}
${targetFilePath ? `File: ${targetFilePath}\n\nContent:\n\`\`\`\n${fileContent.slice(0, 3000)}\n\`\`\`` : ''}

User request: ${state.userQuery}

Output ONLY valid Mermaid syntax — no code fences, no prose, no explanation.`;

    const response = await llm.invoke([
      new SystemMessage('You are a diagramming expert. Output only valid Mermaid diagram syntax.'),
      new HumanMessage(prompt),
    ]);

    return { outputType: 'mermaid', outputRef: (response.content as string).trim() };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Micro Logic Node Error:', message);
    return { outputType: 'mermaid', outputRef: 'graph TD\n  A[Start] --> B[Processing] --> C[End]' };
  }
}

export async function diagramNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- DIAGRAM NODE ---');
  try {
    const llm = getLLM('standard', 0);

    // Read target file content if one was identified
    const targetFileName = state.fileRef ? (store.get(state.fileRef) as string | null) : null;
    const targetFilePath = targetFileName && state.repoPath ? path.join(state.repoPath, targetFileName) : null;
    let fileContent = '';
    if (targetFilePath) {
      try { fileContent = fs.readFileSync(targetFilePath, 'utf-8'); } catch { /* not found */ }
    }

    // Gather repo file listing for broader context
    let fileListing = '';
    if (state.repoPath) {
      try {
        const walk = (dir: string, depth = 0): string[] => {
          if (depth > 3) return [];
          return fs.readdirSync(dir).flatMap(name => {
            const full = path.join(dir, name);
            if (name.startsWith('.') || name === 'node_modules') return [];
            try {
              return fs.statSync(full).isDirectory() ? walk(full, depth + 1) : [path.relative(state.repoPath, full)];
            } catch { return []; }
          });
        };
        fileListing = walk(state.repoPath).slice(0, 100).join('\n');
      } catch { /* ignore */ }
    }

    const prompt = `Generate a Mermaid diagram that directly answers the user's request.
Repository: ${state.repoPath}
${targetFilePath && fileContent ? `Target file: ${targetFilePath}\n\nContent:\n\`\`\`\n${fileContent.slice(0, 3000)}\n\`\`\`` : fileListing ? `File tree (truncated):\n${fileListing}` : ''}

User request: ${state.userQuery}

Choose the most appropriate diagram type (flowchart, graph, sequenceDiagram, classDiagram, erDiagram, etc.).
Output ONLY valid Mermaid syntax — no code fences, no prose, no explanation.`;

    const response = await llm.invoke([
      new SystemMessage('You are a diagramming expert. Output only valid Mermaid diagram syntax with no markdown fences.'),
      new HumanMessage(prompt),
    ]);

    const raw = (response.content as string).trim();
    // Strip accidental code fences the LLM may include despite instructions
    const cleaned = raw.replace(/^```(?:mermaid)?\s*/i, '').replace(/\s*```$/, '').trim();

    return { outputType: 'mermaid', outputRef: cleaned };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Diagram Node Error:', message);
    return {
      outputType: 'markdown',
      outputRef: `Diagram generation failed: ${message}`,
    };
  }
}

export async function macro_structure_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MACRO STRUCTURE NODE ---');
  try {
    const llm = getLLM('standard', 0);
    const prompt = `Analyze the project structure of ${state.repoPath}.
    Identify the main architectural components.
    User query: ${state.userQuery}`;

    const stream = await llm.stream([
      new SystemMessage('You are a senior software architect.'),
      new HumanMessage(prompt),
    ]);

    let full = '';
    for await (const chunk of stream) {
      const token = typeof chunk.content === 'string' ? chunk.content : '';
      full += token;
      tokenEmitter.emit(state.sessionId, token);
    }

    return { outputType: 'markdown', outputRef: full };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Macro Node Error:', message);
    return {
      outputType: 'markdown',
      outputRef: 'Architectural analysis paused due to reasoning cluster availability.',
    };
  }
}

export async function deepExplanation_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- DEEP EXPLANATION NODE ---');
  try {
    const llm = getLLM('complex', 0.1);

    // Wait for background indexing to finish before querying
    await ragIndexer.waitForIndex(state.sessionId || 'default');

    // Retrieve relevant code chunks via RAG
    const chunks = await ragIndexer.retrieve(
      state.userQuery,
      state.sessionId || 'default'
    );

    const ragContext = chunks.length > 0
      ? `\nRelevant code from the repository:\n\`\`\`\n${chunks.join('\n\n---\n')}\n\`\`\`\n`
      : '';

    const prompt = `Explain how the following works in ${state.repoPath}:
${state.userQuery}
${ragContext}
Focus on technical details and data flow.`;

    const stream = await llm.stream([
      new SystemMessage('You are a technical lead explaining a codebase.'),
      new HumanMessage(prompt),
    ]);

    let full = '';
    for await (const chunk of stream) {
      const token = typeof chunk.content === 'string' ? chunk.content : '';
      full += token;
      tokenEmitter.emit(state.sessionId, token);
    }

    return { outputType: 'markdown', outputRef: full };
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

    // Resolve the actual file path on disk
    const targetFileName = state.fileRef
      ? (store.get(state.fileRef) as string | null)
      : null;
    const targetFilePath =
      targetFileName && state.repoPath
        ? path.join(state.repoPath, targetFileName)
        : null;

    // Read the real file content if it exists
    let fileContent = '';
    if (targetFilePath) {
      try { fileContent = fs.readFileSync(targetFilePath, 'utf-8'); } catch { /* not found */ }
    }

    const prompt = `You are performing a structural code refactor.
Repository: ${state.repoPath}
${targetFilePath ? `Target file: ${targetFilePath}\n\nCurrent content:\n\`\`\`\n${fileContent.slice(0, 3000)}\n\`\`\`` : ''}

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
    const { modified, appliedBlocks, error } = applySearchReplace(fileContent, llmOutput);

    if (error) {
      return {
        outputType: 'markdown',
        outputRef: `Refactor could not be applied: ${error}\n\nRaw suggestion:\n\`\`\`\n${llmOutput}\n\`\`\``,
      };
    }

    // Store the full diff in session store for server-side file write on accept
    const diffRef = store.put({ original: fileContent, modified, appliedBlocks, filePath: targetFilePath });

    // Send inline JSON so the client can render the diff immediately
    const diffPayload = JSON.stringify({ original: fileContent, modified, appliedBlocks, filePath: targetFilePath });

    return {
      outputType: 'diff_proposal',
      outputRef: diffPayload,
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

export async function errorNode(_state: AgentState): Promise<Partial<AgentState>> {
  return {
    error: "I'm not sure how to help with that yet. Try asking about architecture, code flow, or refactoring.",
  };
}

export function routeByIntent(state: AgentState) {
  if (state.error) return 'error_handler';
  return state.intent ?? 'error_handler';
}
