import fs from 'fs';
import path from 'path';
import { AgentState } from './state.ts';
import { getLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
import { applySearchReplace } from '../tools/diff_engine.ts';
import { ragIndexer } from '../tools/rag_indexer.ts';
import { graphIndexer } from '../tools/graph_indexer.ts';
import { z } from 'zod';
import { SystemMessage, HumanMessage } from '@langchain/core/messages';
import { tokenEmitter } from '../infrastructure/token_emitter.ts';

/**
 * nodes.ts
 * Implementation of the LangGraph nodes.
 */

const RouterSchema = z.object({
  intent: z.enum(['macro_structure', 'micro_logic', 'diagram', 'deep_explanation', 'refactor', 'test', 'error']),
  target_files: z.array(z.string()),
  confidence: z.number(),
});

function historyContext(state: AgentState): string {
  if (!state.conversationHistory) return '';
  try {
    const turns = JSON.parse(state.conversationHistory) as { role: string; content: string }[];
    if (turns.length === 0) return '';
    const lines = turns.slice(-6).map(t => `${t.role === 'user' ? 'User' : 'Assistant'}: ${t.content.slice(0, 300)}`);
    return `\nPrevious conversation:\n${lines.join('\n')}\n`;
  } catch { return ''; }
}

function gitContext(state: AgentState): string {
  if (!state.gitDiff) return '';
  return `\nRecent git changes:\n\`\`\`diff\n${state.gitDiff.slice(0, 2000)}\n\`\`\`\n`;
}

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
    - test: Generate unit or integration tests for a file or function.
    ${historyContext(state)}
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
    await graphIndexer.waitForGraph(state.sessionId);
    const query = state.userQuery.toLowerCase();

    // ── Path 1: dependency / import / architecture diagram → use real graph ──
    const isDependencyQuery = /depend|import|architecture|module|structure|graph|map|tree|topology/.test(query);
    if (isDependencyQuery) {
      const rootFiles = state.targetFiles?.length ? state.targetFiles : undefined;
      const mermaidFromGraph = graphIndexer.toMermaid(state.sessionId, rootFiles);
      if (mermaidFromGraph) {
        return { outputType: 'mermaid', outputRef: mermaidFromGraph };
      }
    }

    // ── Path 2: class / inheritance diagram → use real graph ─────────────────
    const isClassQuery = /class|inherit|hierarch|extend|interface|uml/.test(query);
    if (isClassQuery) {
      const classDiagram = graphIndexer.toClassDiagram(state.sessionId, state.targetFiles);
      if (classDiagram) {
        return { outputType: 'mermaid', outputRef: classDiagram };
      }
    }

    // ── Path 3: LLM-generated diagram enriched with graph context ────────────
    const llm = getLLM('standard', 0);

    const targetFileName = state.fileRef ? (store.get(state.fileRef) as string | null) : null;
    const targetFilePath = targetFileName && state.repoPath ? path.join(state.repoPath, targetFileName) : null;
    let fileContent = '';
    if (targetFilePath) {
      try { fileContent = fs.readFileSync(targetFilePath, 'utf-8'); } catch { /* not found */ }
    }

    // Enrich prompt with graph context for identified files
    const graphContext = state.targetFiles?.length
      ? state.targetFiles.map(f => graphIndexer.getFileContext(f, state.sessionId)).filter(Boolean).join('\n')
      : graphIndexer.getSummary(state.sessionId);

    const prompt = `Generate a Mermaid diagram that directly answers the user's request.
Repository: ${state.repoPath}
${targetFilePath && fileContent ? `Target file: ${targetFilePath}\n\nContent:\n\`\`\`\n${fileContent.slice(0, 3000)}\n\`\`\`` : ''}
${graphContext ? `\nKnowledge graph context:\n${graphContext}` : ''}

User request: ${state.userQuery}

Choose the most appropriate diagram type (flowchart, graph, sequenceDiagram, classDiagram, erDiagram, etc.).
Output ONLY valid Mermaid syntax — no code fences, no prose, no explanation.`;

    const response = await llm.invoke([
      new SystemMessage('You are a diagramming expert. Output only valid Mermaid diagram syntax with no markdown fences.'),
      new HumanMessage(prompt),
    ]);

    const raw = (response.content as string).trim();
    const cleaned = raw.replace(/^```(?:mermaid)?\s*/i, '').replace(/\s*```$/, '').trim();
    return { outputType: 'mermaid', outputRef: cleaned };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Diagram Node Error:', message);
    return { outputType: 'markdown', outputRef: `Diagram generation failed: ${message}` };
  }
}

export async function macro_structure_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MACRO STRUCTURE NODE ---');
  try {
    const llm = getLLM('standard', 0);
    const prompt = `Analyze the project structure of ${state.repoPath}.
    Identify the main architectural components.
    ${historyContext(state)}${gitContext(state)}
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

    // Wait for both RAG and knowledge graph to finish
    await Promise.all([
      ragIndexer.waitForIndex(state.sessionId || 'default'),
      graphIndexer.waitForGraph(state.sessionId || 'default'),
    ]);

    // RAG: semantically similar code chunks
    const chunks = await ragIndexer.retrieve(state.userQuery, state.sessionId || 'default');
    const ragContext = chunks.length > 0
      ? `\nRelevant code chunks (RAG):\n\`\`\`\n${chunks.join('\n\n---\n')}\n\`\`\`\n`
      : '';

    // Graph: structurally related files and symbols
    const { symbols, relatedFiles } = graphIndexer.getContextForQuery(state.userQuery, state.sessionId || 'default');
    const graphCtx = symbols.length > 0
      ? `\nKnowledge graph — related symbols: ${symbols.map(s => `${s.type} ${s.name} in ${s.file}`).join(', ')}\nRelated files: ${relatedFiles.join(', ')}\n`
      : graphIndexer.getSummary(state.sessionId || 'default')
        ? `\n${graphIndexer.getSummary(state.sessionId || 'default')}\n`
        : '';

    const prompt = `Explain how the following works in ${state.repoPath}:
${state.userQuery}
${ragContext}${graphCtx}${historyContext(state)}${gitContext(state)}
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

    // Resolve all target files (multi-file support)
    const targetFileNames: string[] = state.targetFiles?.length
      ? state.targetFiles
      : state.fileRef ? [store.get(state.fileRef) as string].filter(Boolean) : [];

    const fileDiffs: { filePath: string; original: string; modified: string; appliedBlocks: number }[] = [];

    for (const fileName of targetFileNames.slice(0, 5)) {
      const targetFilePath = state.repoPath ? path.join(state.repoPath, fileName) : null;
      let fileContent = '';
      if (targetFilePath) {
        try { fileContent = fs.readFileSync(targetFilePath, 'utf-8'); } catch { continue; }
      }

      // Graph context: what imports this file (impact awareness)
      const graphFileCtx = graphIndexer.getFileContext(fileName, state.sessionId);

      const prompt = `You are performing a structural code refactor.
Repository: ${state.repoPath}
${targetFilePath ? `Target file: ${targetFilePath}\n\nCurrent content:\n\`\`\`\n${fileContent.slice(0, 3000)}\n\`\`\`` : ''}
${graphFileCtx ? `\nKnowledge graph context:\n${graphFileCtx}\n` : ''}${gitContext(state)}${historyContext(state)}
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
        new HumanMessage(prompt),
      ]);

      const llmOutput = response.content as string;
      const { modified, appliedBlocks, error } = applySearchReplace(fileContent, llmOutput);

      if (!error && appliedBlocks > 0) {
        fileDiffs.push({ filePath: targetFilePath!, original: fileContent, modified, appliedBlocks });
      }
    }

    if (fileDiffs.length === 0) {
      return {
        outputType: 'markdown',
        outputRef: 'No applicable changes found. Try being more specific about what to change and which file.',
      };
    }

    const diffRef = store.put(fileDiffs);
    const diffPayload = JSON.stringify(fileDiffs);

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

export async function testNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- TEST NODE ---');
  try {
    const llm = getLLM('complex', 0.1);

    const targetFileName = state.fileRef ? (store.get(state.fileRef) as string | null) : null;
    const targetFilePath = targetFileName && state.repoPath ? path.join(state.repoPath, targetFileName) : null;

    let fileContent = '';
    if (targetFilePath) {
      try { fileContent = fs.readFileSync(targetFilePath, 'utf-8'); } catch { /* not found */ }
    }

    // Detect test framework from package.json
    let testFramework = 'the appropriate test framework';
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(state.repoPath, 'package.json'), 'utf-8'));
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };
      if (deps['vitest']) testFramework = 'Vitest';
      else if (deps['jest']) testFramework = 'Jest';
      else if (deps['mocha']) testFramework = 'Mocha';
      else if (deps['pytest']) testFramework = 'pytest';
    } catch { /* ignore */ }

    // Graph: find what this file imports so we know what to mock
    const targetRelPath = targetFileName ?? '';
    const graphFileCtx = graphIndexer.getFileContext(targetRelPath, state.sessionId);
    const deps = targetRelPath ? graphIndexer.getDependencies(targetRelPath, state.sessionId) : [];
    const mockHints = deps.length
      ? `Dependencies to consider mocking: ${deps.slice(0, 8).join(', ')}`
      : '';

    const prompt = `Generate comprehensive tests using ${testFramework}.
Repository: ${state.repoPath}
${targetFilePath && fileContent ? `File to test: ${targetFilePath}\n\nSource:\n\`\`\`\n${fileContent.slice(0, 4000)}\n\`\`\`` : ''}
${graphFileCtx ? `\nKnowledge graph context:\n${graphFileCtx}\n` : ''}${mockHints ? `${mockHints}\n` : ''}${historyContext(state)}
User request: ${state.userQuery}

Include:
- Unit tests for each exported function/class
- Edge cases and error conditions
- Mock all external dependencies identified above
- Clear describe/it block names

Output only the test file content — no explanation.`;

    const stream = await llm.stream([
      new SystemMessage('You are a senior engineer writing thorough, idiomatic tests.'),
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
    console.error('Test Node Error:', message);
    return {
      outputType: 'markdown',
      outputRef: `Test generation failed: ${message}`,
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
