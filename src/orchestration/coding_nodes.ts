import path from 'path';
import { CodingAgentState } from './state.ts';
import { getLLM, getComplexLLM } from '../infrastructure/llm_factory.ts';
import { store } from '../infrastructure/session_store.ts';
import { emitRegistry } from '../infrastructure/emit_registry.ts';
import { applySearchReplace } from '../tools/diff_engine.ts';
import { makeAgentTools } from '../tools/agent_tools.ts';
import { LLMConfig } from '../types/llm_config.ts';
import { SelectionContext } from '../types/selection_context.ts';
import { SystemMessage, HumanMessage, ToolMessage, AIMessage, BaseMessage } from '@langchain/core/messages';
import { BaseChatModel } from '@langchain/core/language_models/chat_models';
import { StructuredToolInterface } from '@langchain/core/tools';

// ReAct tool-calling loop — emits live tool_call/tool_result events to UI
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

    for (const tc of toolCalls) {
      emitRegistry.emit(sessionId, 'tool_call', { tool: tc.name, args: tc.args, iteration: i + 1 });
    }

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
    new HumanMessage('Based on everything gathered, provide your final answer now.'),
  ]);
  return typeof final.content === 'string' ? final.content : JSON.stringify(final.content);
}

function resolveConfig(state: CodingAgentState): LLMConfig | undefined {
  if (!state.llmConfigRef) return undefined;
  return store.get(state.llmConfigRef) as LLMConfig | undefined;
}

function resolveSelection(state: CodingAgentState): SelectionContext | null {
  if (!state.selectionRef) return null;
  return store.get(state.selectionRef) as SelectionContext | null;
}

function getPreloadedContent(selection: SelectionContext | null): Record<string, string> {
  if (!selection?.contentRef) return {};
  return (store.get(selection.contentRef) as Record<string, string> | null) ?? {};
}

function selectionNote(selection: SelectionContext | null): string {
  if (!selection || selection.resolvedFiles.length === 0) return '';
  const names = selection.resolvedFiles.map(f => path.basename(f)).join(', ');
  return `\n\nFocus on these selected files: ${names}`;
}

function formatPreloaded(contentMap: Record<string, string>, maxPerFile = 4000): string {
  return Object.entries(contentMap)
    .map(([file, content]) => `\`\`\`\n// ${file}\n${content.slice(0, maxPerFile)}\n\`\`\``)
    .join('\n\n');
}

// ── Explain ──────────────────────────────────────────────────────────────────

export async function explainNode(state: CodingAgentState): Promise<Partial<CodingAgentState>> {
  try {
    const config = resolveConfig(state);
    const selection = resolveSelection(state);
    const contentMap = getPreloadedContent(selection);
    const llm = getComplexLLM(config);
    const tools = makeAgentTools(state.repoPath, state.sessionId, state.graphRef);

    const preloaded = formatPreloaded(contentMap);

    const output = await runAgentLoop(
      llm,
      tools,
      `You are a senior software engineer explaining code to a colleague.
Use read_file, search_codebase, and grep_codebase to gather any additional context.
Produce a clear Markdown explanation: what the code does, key patterns, data flow, and any notable design decisions.
Reference actual function and variable names.${selectionNote(selection)}`,
      `Repository: ${state.repoPath}
${preloaded ? `\nSelected files:\n${preloaded}\n` : ''}
Question: ${state.userQuery}`,
      state.sessionId
    );

    return { outputType: 'markdown', outputRef: output };
  } catch (error: unknown) {
    return { outputType: 'markdown', outputRef: `Explanation failed: ${error instanceof Error ? error.message : String(error)}` };
  }
}

// ── Diagram ───────────────────────────────────────────────────────────────────

export async function diagramNode(state: CodingAgentState): Promise<Partial<CodingAgentState>> {
  try {
    const config = resolveConfig(state);
    const selection = resolveSelection(state);
    const contentMap = getPreloadedContent(selection);
    const llm = getLLM(config);
    const tools = makeAgentTools(state.repoPath, state.sessionId, state.graphRef);

    const preloaded = Object.entries(contentMap)
      .map(([file, content]) => `// ${file}\n${content.slice(0, 3000)}`)
      .join('\n\n---\n\n');

    const output = await runAgentLoop(
      llm,
      tools,
      `You are a software architect creating Mermaid diagrams.
Use read_file and grep_codebase to understand the code structure.

Choose the most appropriate diagram type:
- "flowchart TD" → control flow, data flow, decision logic
- "sequenceDiagram" → request/response, API calls, async flows
- "classDiagram" → class/interface structure, inheritance
- "stateDiagram-v2" → state machines, lifecycle
- "erDiagram" → data models, schemas

Return ONLY the Mermaid diagram — no prose, no code fences.${selectionNote(selection)}`,
      `Repository: ${state.repoPath}
${preloaded ? `\nSelected code:\n${preloaded}\n` : ''}
Request: ${state.userQuery}`,
      state.sessionId
    );

    const mermaid = output.replace(/^```[a-z]*\n?/i, '').replace(/\n?```$/i, '').trim();
    return { outputType: 'mermaid', outputRef: mermaid };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    return { outputType: 'mermaid', outputRef: `graph TD\n  A[Error] --> B["${msg}"]` };
  }
}

// ── Code modification (refactor / fix_bug / add_feature) ─────────────────────

export async function codeModifyNode(state: CodingAgentState): Promise<Partial<CodingAgentState>> {
  try {
    const config = resolveConfig(state);
    const selection = resolveSelection(state);
    const contentMap = getPreloadedContent(selection);
    const llm = getComplexLLM(config);
    const tools = makeAgentTools(state.repoPath, state.sessionId, state.graphRef);
    const sid = state.sessionId;

    // Use selected files directly if available, otherwise let agent explore
    let filePlan: { file: string; content: string }[] = Object.entries(contentMap)
      .map(([file, content]) => ({ file, content }));

    if (filePlan.length === 0) {
      emitRegistry.emit(sid, 'log', { message: '[Coding] No selection — exploring repo...' });

      const exploration = await runAgentLoop(
        llm,
        tools,
        `You are a senior engineer preparing a multi-file code change.
Use list_files, read_file, and grep_codebase to find every file that must change.
Read each file in full. Output ONLY a JSON array — no prose, no fences:
[{ "file": "relative/path.ts", "content": "<exact current content>" }]`,
        `Repository: ${state.repoPath}\nRequest: ${state.userQuery}`,
        sid
      );

      try {
        const raw = exploration.replace(/^```json\n?/i, '').replace(/\n?```$/i, '').trim();
        const parsed = JSON.parse(raw);
        filePlan = Array.isArray(parsed) ? parsed : [parsed];
      } catch {
        return {
          outputType: 'markdown',
          outputRef: `Could not identify files to modify.\n\nAgent output:\n\`\`\`\n${exploration}\n\`\`\``,
        };
      }
    } else {
      emitRegistry.emit(sid, 'log', { message: `[Coding] Modifying ${filePlan.length} selected file(s)...` });
    }

    if (filePlan.length === 0) {
      return { outputType: 'markdown', outputRef: 'No files identified for this change.' };
    }

    const taskVerb: Record<string, string> = {
      refactor: 'Refactor',
      fix_bug: 'Fix the following bug in',
      add_feature: 'Add the following feature to',
    };
    const verb = taskVerb[state.task] ?? 'Modify';

    const fileDiffs: { original: string; modified: string; appliedBlocks: number; filePath: string | null }[] = [];

    for (const plan of filePlan) {
      const targetFilePath = plan.file && state.repoPath
        ? path.join(state.repoPath, plan.file)
        : null;

      const diffResponse = await llm.invoke([
        new SystemMessage('You are a senior engineer making precise, minimal code changes.'),
        new HumanMessage(`${verb}: ${state.userQuery}

File: ${plan.file}

Current content:
\`\`\`
${plan.content.slice(0, 4000)}
\`\`\`

Produce SEARCH/REPLACE blocks for every change needed:
<<<<
<exact lines to find>
====
<replacement lines>
>>>>

Only emit the blocks — no other text.`),
      ]);

      const llmOutput = diffResponse.content as string;
      const { modified, appliedBlocks, error } = applySearchReplace(plan.content, llmOutput);

      if (error) {
        emitRegistry.emit(sid, 'log', { message: `[Coding] Diff failed for ${plan.file}: ${error}` });
        continue;
      }

      fileDiffs.push({ original: plan.content, modified, appliedBlocks, filePath: targetFilePath });
    }

    if (fileDiffs.length === 0) {
      return { outputType: 'markdown', outputRef: 'No diffs could be generated for this request.' };
    }

    const diffRef = store.put({ files: fileDiffs });
    return { outputType: 'diff_proposal', outputRef: JSON.stringify({ files: fileDiffs }), pendingDiffId: diffRef };
  } catch (error: unknown) {
    return { outputType: 'markdown', outputRef: `Code modification failed: ${error instanceof Error ? error.message : String(error)}` };
  }
}

// ── Generate tests ────────────────────────────────────────────────────────────

export async function generateTestsNode(state: CodingAgentState): Promise<Partial<CodingAgentState>> {
  try {
    const config = resolveConfig(state);
    const selection = resolveSelection(state);
    const contentMap = getPreloadedContent(selection);
    const llm = getComplexLLM(config);
    const tools = makeAgentTools(state.repoPath, state.sessionId, state.graphRef);

    const preloaded = formatPreloaded(contentMap);

    const output = await runAgentLoop(
      llm,
      tools,
      `You are a senior engineer writing comprehensive tests.
Use read_file and grep_codebase to understand the existing test patterns and framework.
Generate tests covering: happy path, edge cases, and error handling.
Follow the project's existing test style. Return complete, runnable test code in Markdown.${selectionNote(selection)}`,
      `Repository: ${state.repoPath}
${preloaded ? `\nCode to test:\n${preloaded}\n` : ''}
Test request: ${state.userQuery}`,
      state.sessionId
    );

    return { outputType: 'markdown', outputRef: output };
  } catch (error: unknown) {
    return { outputType: 'markdown', outputRef: `Test generation failed: ${error instanceof Error ? error.message : String(error)}` };
  }
}

// ── Router ────────────────────────────────────────────────────────────────────

export function routeByTask(state: CodingAgentState): string {
  switch (state.task) {
    case 'explain': return 'explain';
    case 'diagram': return 'diagram';
    case 'refactor':
    case 'fix_bug':
    case 'add_feature': return 'code_modify';
    case 'generate_tests': return 'generate_tests';
    default: return 'explain';
  }
}
