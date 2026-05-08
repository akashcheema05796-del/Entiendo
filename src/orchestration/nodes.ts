import path from 'path';
import { AgentState } from './state.ts';
import { getLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
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

// Runs a ReAct-style tool-calling loop until the LLM stops calling tools or hits maxIterations.
async function runAgentLoop(
  llm: BaseChatModel,
  tools: readonly StructuredToolInterface[],
  systemPrompt: string,
  userQuery: string,
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

    // Execute all tool calls in parallel
    const results = await Promise.all(
      toolCalls.map(async tc => {
        const t = toolMap.get(tc.name);
        const result = t ? await t.invoke(tc.args) : `Unknown tool: ${tc.name}`;
        return new ToolMessage({ content: String(result), tool_call_id: tc.id ?? '' });
      })
    );
    messages.push(...results);
  }

  // Max iterations reached — ask for a final answer based on gathered context
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
    - micro_logic: UML, flowcharts, logic within a single file.
    - deep_explanation: RAG-based search, "how does X work?".
    - refactor: Editing code, fixing bugs, optimization.

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
      `Repository: ${state.repoPath}\nUser query: ${state.userQuery}`
    );

    return { outputType: 'markdown', outputRef: output };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('Macro Node Error:', message);
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
      `You are a software engineer creating a Mermaid diagram.
Use read_file to read the target file, then grep_codebase to trace function calls
or class relationships if needed.
Return ONLY a valid Mermaid diagram (starting with "graph TD" or "sequenceDiagram" etc.)
with no surrounding prose or code fences.`,
      `Repository: ${state.repoPath}
Target file: ${targetFile || '(not specified — pick the most relevant file for the query)'}
User query: ${state.userQuery}`
    );

    // Strip accidental code fences the LLM might add
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
      `Repository: ${state.repoPath}\nQuestion: ${state.userQuery}`
    );

    return { outputType: 'markdown', outputRef: output };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return { outputType: 'markdown', outputRef: `Deep analysis failed: ${message}` };
  }
}

export async function refactorNode(state: AgentState): Promise<Partial<AgentState>> {
  console.log('--- REFACTOR NODE ---');
  try {
    const llm = getLLM('complex', 0.1);
    const tools = makeAgentTools(state.repoPath, state.sessionId || 'default');

    // First: let the agent explore and identify the exact file + content to change
    const exploration = await runAgentLoop(
      llm,
      tools,
      `You are a senior engineer preparing a code refactor.
Use list_files, read_file, and grep_codebase to locate and read the exact file(s)
that need to be changed. Once you have read the relevant file content, output a JSON
object with two fields:
  "file": the relative file path
  "content": the full current file content (copy it exactly as read)
Output ONLY that JSON object, no other text.`,
      `Repository: ${state.repoPath}\nRefactor request: ${state.userQuery}`
    );

    let fileContent = '';
    let targetFilePath: string | null = null;

    try {
      const parsed = JSON.parse(exploration.replace(/^```json\n?/i, '').replace(/\n?```$/i, '').trim());
      fileContent = parsed.content ?? '';
      if (parsed.file && state.repoPath) {
        targetFilePath = path.join(state.repoPath, parsed.file);
      }
    } catch {
      // Fallback: use exploration text as context
      fileContent = exploration;
    }

    // Second: produce the SEARCH/REPLACE diff
    const diffPrompt = `You are performing a precise code refactor.
${targetFilePath ? `Target file: ${targetFilePath}` : ''}

Current file content:
\`\`\`
${fileContent.slice(0, 4000)}
\`\`\`

Produce SEARCH/REPLACE blocks in this exact format for every change:
<<<<
<exact lines to find>
====
<replacement lines>
>>>>

Only emit the blocks — no prose.`;

    const response = await llm.invoke([
      new SystemMessage('You are a senior engineer performing precise code refactors.'),
      new HumanMessage(`${diffPrompt}\n\nRequest: ${state.userQuery}`),
    ]);

    const llmOutput = response.content as string;
    const { modified, appliedBlocks, error } = applySearchReplace(fileContent, llmOutput);

    if (error) {
      return {
        outputType: 'markdown',
        outputRef: `Refactor could not be applied: ${error}\n\nRaw suggestion:\n\`\`\`\n${llmOutput}\n\`\`\``,
      };
    }

    const diffRef = store.put({ original: fileContent, modified, appliedBlocks, filePath: targetFilePath });
    const diffPayload = JSON.stringify({ original: fileContent, modified, appliedBlocks, filePath: targetFilePath });

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
