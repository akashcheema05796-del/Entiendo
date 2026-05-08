import path from 'path';
import { AgentState } from './state.ts';
import { getLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
import { emitRegistry } from '../infrastructure/emit_registry.ts';
import { applySearchReplace } from '../tools/diff_engine.ts';
import { makeAgentTools } from '../tools/agent_tools.ts';
import { z } from 'zod';
import { SystemMessage, HumanMessage, ToolMessage, AIMessage, BaseMessage } from '@langchain/core/messages';
import { BaseChatModel } from '@langchain/core/language_models/chat_models';
import { StructuredToolInterface } from '@langchain/core/tools';

const RouterSchema = z.object({
  intent: z.enum(['macro_structure', 'micro_logic', 'deep_explanation', 'refactor', 'error']),
  target_files: z.array(z.string()),
  confidence: z.number(),
});

// ReAct-style tool-calling loop. Emits live tool_call events to the UI via emitRegistry.
async function runAgentLoop(
  llm: BaseChatModel,
  tools: readonly StructuredToolInterface[],
  systemPrompt: string,
  userQuery: string,
  sessionId: string,
  maxIterations = 8
): Promise<string> {
  const llmWithTools = (llm as any).bindTools(tools);
  const toolMap = new Map(tools.map(t => [t.name, t]));

  const messages: BaseMessage[] = [
    new SystemMessage(systemPrompt),
    new HumanMessage(userQuery),
  ];

  for (let i = 0; i < maxIterations; i++) {
    const response = await llmWithTools.invoke(messages) as AIMessage;
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    // Emit each tool call to the UI before executing
    for (const tc of toolCalls) {
      emitRegistry.emit(sessionId, 'tool_call', {
        tool: tc.name,
        args: tc.args,
        iteration: i + 1,
      });
    }

    // Execute all tool calls in parallel
    const results = await Promise.all(
      toolCalls.map(async tc => {
        const t = toolMap.get(tc.name);
        const result = t ? await t.invoke(tc.args) : `Unknown tool: ${tc.name}`;
        const resultStr = String(result);

        emitRegistry.emit(sessionId, 'tool_result', {
          tool: tc.name,
          preview: resultStr.slice(0, 120) + (resultStr.length > 120 ? '…' : ''),
        });

        return new ToolMessage({ content: resultStr, tool_call_id: tc.id ?? '' });
      })
    );
    messages.push(...results);
  }

  const final = await llm.invoke([
    ...messages,
    new HumanMessage('Based on everything you have gathered, provide your final answer now.'),
  ]);
  return typeof final.content === 'string' ? final.content : JSON.stringify(final.content);
}

export async function entryNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- ENTRY NODE ---');
  try {
    const llm = getLLM('standard', 0);
    const structuredLlm = (llm as any).withStructuredOutput(RouterSchema);

    const prompt = `Classify user intent for codebase analysis.
    - macro_structure: Visualization, dependency graphs, architectural overview.
    - micro_logic: UML, flowcharts, logic within a single file or feature.
    - deep_explanation: RAG-based search, "how does X work?".
    - refactor: Editing code, fixing bugs, optimization, renaming.

    User query: ${state.userQuery}`;

    const result = await structuredLlm.invoke([
      new SystemMessage('You are a senior codebase architect router.'),
      new HumanMessage(prompt),
    ]) as z.infer<typeof RouterSchema>;

    let fileRef: string | null = null;
    if (result.target_files.length > 0) {
      fileRef = store.put(result.target_files[0]);
    }

    return { intent: result.intent, targetFiles: result.target_files, fileRef };
  } catch (error: unknown) {
    console.error('Entry Node Error:', error);
    return { intent: 'macro_structure', targetFiles: [], fileRef: null };
  }
}

export async function macro_structure_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MACRO STRUCTURE NODE ---');
  try {
    const llm = getLLM('standard', 0);
    const tools = makeAgentTools(state.repoPath, state.sessionId || 'default');

    const output = await runAgentLoop(
      llm,
      tools,
      `You are a senior software architect analyzing a codebase.
Use list_files to explore the repo structure, then read_file on key files
(package.json, main entry points, config files) to understand the architecture.
Produce a clear Markdown report covering: tech stack, main modules, data flow,
and architectural patterns. Be specific — reference actual file names.`,
      `Repository: ${state.repoPath}\nUser query: ${state.userQuery}`,
      state.sessionId || 'default'
    );

    return { outputType: 'markdown', outputRef: output };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return { outputType: 'markdown', outputRef: `Architecture analysis failed: ${message}` };
  }
}

export async function microLogicNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- MICRO LOGIC NODE ---');
  try {
    const llm = getLLM('standard', 0.1);
    const tools = makeAgentTools(state.repoPath, state.sessionId || 'default');
    const targetFile = state.targetFiles?.[0] ?? '';

    const output = await runAgentLoop(
      llm,
      tools,
      `You are a software engineer creating Mermaid diagrams.
Use read_file to read the target file, then grep_codebase to trace calls or relationships.

Choose the most appropriate Mermaid diagram type for the query:
- "graph TD" or "flowchart TD"  → control flow, data flow, decision logic
- "sequenceDiagram"             → request/response cycles, API calls, async flows
- "classDiagram"                → class/interface structure, inheritance, composition
- "stateDiagram-v2"             → state machines, lifecycle management
- "erDiagram"                   → data models, database schemas

Return ONLY the Mermaid diagram. No prose, no code fences, no explanation.`,
      `Repository: ${state.repoPath}
Target file: ${targetFile || '(not specified — pick the most relevant file for the query)'}
User query: ${state.userQuery}`,
      state.sessionId || 'default'
    );

    const mermaid = output.replace(/^```[a-z]*\n?/i, '').replace(/\n?```$/i, '').trim();
    return { outputType: 'mermaid', outputRef: mermaid };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return { outputType: 'mermaid', outputRef: `graph TD\n  A[Error] --> B["${message}"]` };
  }
}

export async function deepExplanation_node(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- DEEP EXPLANATION NODE ---');
  try {
    const llm = getLLM('complex', 0.1);
    const tools = makeAgentTools(state.repoPath, state.sessionId || 'default');

    const output = await runAgentLoop(
      llm,
      tools,
      `You are a technical lead explaining a codebase to a senior engineer.
Use search_codebase to find semantically relevant code, then read_file to read
the actual implementations, and grep_codebase to trace how things connect.
Gather enough evidence before answering. Be precise: quote file paths and
line-level details. Format your answer in Markdown.`,
      `Repository: ${state.repoPath}\nQuestion: ${state.userQuery}`,
      state.sessionId || 'default'
    );

    return { outputType: 'markdown', outputRef: output };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return { outputType: 'markdown', outputRef: `Deep analysis failed: ${message}` };
  }
}

interface FilePlan {
  file: string;
  content: string;
}

export async function refactorNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- REFACTOR NODE ---');
  try {
    const llm = getLLM('complex', 0.1);
    const tools = makeAgentTools(state.repoPath, state.sessionId || 'default');
    const sid = state.sessionId || 'default';

    // Phase 1: agent explores the repo and identifies ALL files that need to change
    const exploration = await runAgentLoop(
      llm,
      tools,
      `You are a senior engineer preparing a multi-file code refactor.
Use list_files, read_file, and grep_codebase to locate every file that must change.
Read each file's content in full.

When done, output ONLY a JSON array — no prose, no fences:
[
  { "file": "relative/path/to/file.ts", "content": "<exact current file content>" },
  { "file": "another/file.ts", "content": "<exact current file content>" }
]`,
      `Repository: ${state.repoPath}\nRefactor request: ${state.userQuery}`,
      sid
    );

    // Parse the file plan — handle single object or array
    let filePlan: FilePlan[] = [];
    try {
      const raw = exploration.replace(/^```json\n?/i, '').replace(/\n?```$/i, '').trim();
      const parsed = JSON.parse(raw);
      filePlan = Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      return {
        outputType: 'markdown',
        outputRef: `Refactor exploration failed to return valid JSON.\n\nAgent output:\n\`\`\`\n${exploration}\n\`\`\``,
      };
    }

    if (filePlan.length === 0) {
      return { outputType: 'markdown', outputRef: 'No files identified for this refactor.' };
    }

    emitRegistry.emit(sid, 'log', { message: `[Refactor] Planning changes across ${filePlan.length} file(s)...` });

    // Phase 2: for each file, generate SEARCH/REPLACE diff
    const fileDiffs: { original: string; modified: string; appliedBlocks: number; filePath: string | null }[] = [];

    for (const plan of filePlan) {
      const targetFilePath = plan.file && state.repoPath
        ? path.join(state.repoPath, plan.file)
        : null;

      const diffResponse = await llm.invoke([
        new SystemMessage('You are a senior engineer performing precise code refactors.'),
        new HumanMessage(`You are refactoring: ${targetFilePath ?? 'unknown file'}

Current content:
\`\`\`
${plan.content.slice(0, 4000)}
\`\`\`

Produce SEARCH/REPLACE blocks in this exact format for every change needed:
<<<<
<exact lines to find>
====
<replacement lines>
>>>>

Only emit the blocks — no other text.

Refactor request: ${state.userQuery}`),
      ]);

      const llmOutput = diffResponse.content as string;
      const { modified, appliedBlocks, error } = applySearchReplace(plan.content, llmOutput);

      if (error) {
        emitRegistry.emit(sid, 'log', { message: `[Refactor] Could not apply diff for ${plan.file}: ${error}` });
        continue;
      }

      fileDiffs.push({ original: plan.content, modified, appliedBlocks, filePath: targetFilePath });
    }

    if (fileDiffs.length === 0) {
      return { outputType: 'markdown', outputRef: 'No diffs could be generated for this refactor request.' };
    }

    const diffRef = store.put({ files: fileDiffs });
    const diffPayload = JSON.stringify({ files: fileDiffs });

    return { outputType: 'diff_proposal', outputRef: diffPayload, pendingDiffId: diffRef };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Refactor Node Error:', message);
    return { outputType: 'markdown', outputRef: `Refactor failed: ${message}` };
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
