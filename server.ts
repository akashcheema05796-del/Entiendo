import express from 'express';
import 'dotenv/config';
import { createServer } from 'http';
import { Server } from 'socket.io';
import path from 'path';
import fs from 'fs';
import { createServer as createViteServer } from 'vite';
import { store } from './src/infrastructure/session_store.ts';
import { emitRegistry } from './src/infrastructure/emit_registry.ts';
import { ragIndexer } from './src/tools/rag_indexer.ts';
import { runUnderstandingAgent } from './src/orchestration/understanding_graph.ts';
import { expandFileNode } from './src/orchestration/understanding_nodes.ts';
import { ProjectGraph, GraphNode } from './src/types/project_graph.ts';
import { LLMConfig, getDefaultLLMConfig } from './src/types/llm_config.ts';

function getFileTree(dir: string, baseDir: string = dir): { name: string; path: string; size: number }[] {
  let results: { name: string; path: string; size: number }[] = [];
  try {
    for (const file of fs.readdirSync(dir)) {
      const filePath = path.join(dir, file);
      const stat = fs.statSync(filePath);
      if (stat.isDirectory()) {
        if (!['node_modules', '.git', 'dist', '__pycache__'].includes(file))
          results = results.concat(getFileTree(filePath, baseDir));
      } else {
        results.push({ name: file, path: path.relative(baseDir, filePath), size: stat.size });
      }
    }
  } catch { /* ignore */ }
  return results;
}

async function resolveWorkspace(input: string): Promise<{ workspacePath: string; cloned: boolean } | { error: string }> {
  const isLocal = /^(\/|\.\/|\.\.\/|~\/)/.test(input) ||
    (process.platform === 'win32' && /^[a-zA-Z]:[\\\/]/.test(input));

  if (isLocal) {
    const resolved = input.replace(/^~(?=\/|$)/, process.env.HOME ?? '');
    if (!fs.existsSync(resolved)) return { error: `Local path not found: ${resolved}` };
    return { workspacePath: path.resolve(resolved), cloned: false };
  }

  const workspacePath = path.join(process.cwd(), 'workspace', input.replace(/[^a-zA-Z0-9_-]/g, '_'));
  const cloned = !fs.existsSync(workspacePath);
  if (cloned) {
    const workspaceDir = path.join(process.cwd(), 'workspace');
    if (!fs.existsSync(workspaceDir)) fs.mkdirSync(workspaceDir, { recursive: true });
    const { execSync } = await import('child_process');
    execSync(`npx -y degit ${input} ${workspacePath} --force`, { timeout: 60_000 });
  }
  return { workspacePath, cloned };
}

async function startServer() {
  const app = express();
  const httpServer = createServer(app);
  const io = new Server(httpServer, { cors: { origin: '*' } });
  const PORT = 3000;

  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);
    const sessionId = socket.id;

    // Per-session mutable state
    let currentWorkspacePath: string | null = null;
    let sessionGraphRef: string | null = null;
    let sessionLLMConfig: LLMConfig = getDefaultLLMConfig();

    emitRegistry.register(sessionId, (event, data) => socket.emit(event as string, data));

    // ── Load workspace + run Understanding Agent ──────────────────────────────
    socket.on('load_workspace', async (data: { path: string }) => {
      try {
        const result = await resolveWorkspace(data.path);
        if ('error' in result) { socket.emit('error', { message: result.error }); return; }

        const { workspacePath, cloned } = result;
        currentWorkspacePath = workspacePath;

        if (cloned) socket.emit('log', { message: '[System] Repository cloned.' });
        else socket.emit('log', { message: `[System] Workspace loaded: ${path.basename(workspacePath)}` });

        // Send file tree (for backward compat)
        const fileTree = getFileTree(workspacePath);
        socket.emit('repo_structure', { tree: fileTree, repo_url: data.path });

        // Check for cached graph
        if (store.isGraphFresh(workspacePath)) {
          const cached = store.loadGraph(workspacePath);
          if (cached) {
            sessionGraphRef = store.put(cached, 7200);
            socket.emit('graph_ready', { nodeCount: cached.nodes.length, edgeCount: cached.edges.length, graphRef: sessionGraphRef, cached: true });
            socket.emit('graph_data', cached);
            socket.emit('log', { message: `[Graph] Loaded from cache: ${cached.nodes.length} nodes, ${cached.edges.length} edges` });
            ragIndexer.indexRepo(workspacePath, sessionId, msg => socket.emit('log', { message: msg })).catch(() => {});
            return;
          }
        }

        // Run Understanding Agent
        socket.emit('log', { message: '[Graph] Indexing project structure...' });
        await runUnderstandingAgent({ sessionId, workspacePath, triggerKind: 'full_index' });

        // After agent runs, the graph is in store — load it
        const built = store.loadGraph(workspacePath);
        if (built) {
          sessionGraphRef = store.put(built, 7200);
          socket.emit('graph_data', built);
        }

        // Start RAG indexing in background
        ragIndexer.indexRepo(workspacePath, sessionId, msg => socket.emit('log', { message: msg })).catch(() => {});

      } catch (error: unknown) {
        socket.emit('error', { message: error instanceof Error ? error.message : String(error) });
      }
    });

    // ── Expand a file node into symbol child nodes ────────────────────────────
    socket.on('expand_node', (data: { nodeId: string }) => {
      if (!currentWorkspacePath || !sessionGraphRef) {
        socket.emit('node_expanded', { nodeId: data.nodeId, childNodes: [], childEdges: [] });
        return;
      }
      const graph = store.get(sessionGraphRef) as ProjectGraph | null;
      const node = graph?.nodes.find(n => n.id === data.nodeId);
      if (!node || node.kind !== 'file') {
        socket.emit('node_expanded', { nodeId: data.nodeId, childNodes: [], childEdges: [] });
        return;
      }
      const { childNodes, childEdges } = expandFileNode(currentWorkspacePath, node);
      socket.emit('node_expanded', { nodeId: data.nodeId, childNodes, childEdges });
    });

    // ── Expand a directory node ───────────────────────────────────────────────
    socket.on('expand_directory', async (data: { relativePath: string }) => {
      if (!currentWorkspacePath) return;
      try {
        socket.emit('log', { message: `[Graph] Expanding directory: ${data.relativePath}` });
        await runUnderstandingAgent({
          sessionId,
          workspacePath: currentWorkspacePath,
          triggerKind: 'directory_expand',
          targetPath: data.relativePath,
        });
      } catch (error: unknown) {
        socket.emit('error', { message: error instanceof Error ? error.message : String(error) });
      }
    });

    // ── Coding query (Phase 3 — full implementation) ──────────────────────────
    socket.on('coding_query', async (data: { query: string; selectedNodeIds: string[]; task: string }) => {
      if (!currentWorkspacePath) { socket.emit('error', { message: 'No workspace loaded.' }); return; }

      const graph = sessionGraphRef ? (store.get(sessionGraphRef) as ProjectGraph | null) : null;

      // Resolve selected nodes to file paths
      const selectedNodes: GraphNode[] = [];
      if (graph && data.selectedNodeIds.length > 0) {
        for (const id of data.selectedNodeIds) {
          const node = graph.nodes.find(n => n.id === id);
          if (node) selectedNodes.push(node);
        }
      }

      const resolvedFiles = selectedNodes
        .filter(n => n.kind === 'file')
        .map(n => path.join(currentWorkspacePath!, n.relativePath));

      const resolvedEdges = graph
        ? graph.edges.filter(e => data.selectedNodeIds.includes(e.source) && data.selectedNodeIds.includes(e.target))
        : [];

      // Build SelectionContext and store it
      const contentMap: Record<string, string> = {};
      for (const filePath of resolvedFiles) {
        try { contentMap[path.relative(currentWorkspacePath!, filePath)] = fs.readFileSync(filePath, 'utf-8').slice(0, 8000); }
        catch { /* skip */ }
      }
      const contentRef = store.put(contentMap, 3600);

      const selectionContext = {
        sessionId,
        selectedNodeIds: data.selectedNodeIds,
        selectionKind: data.selectedNodeIds.length > 1 ? 'freehand' : 'node',
        resolvedFiles,
        resolvedEdges,
        contentRef,
      };
      const selectionRef = store.put(selectionContext, 3600);
      const llmConfigRef = store.put(sessionLLMConfig, 3600);

      try {
        // Import coding graph dynamically (may not exist in Phase 1)
        const { graph: codingGraph } = await import('./src/orchestration/coding_graph.ts');
        const stream = await codingGraph.stream({
          userQuery: data.query,
          repoPath: currentWorkspacePath,
          sessionId,
          selectionRef,
          llmConfigRef,
          graphRef: sessionGraphRef,
          task: data.task,
        });

        for await (const chunk of stream) {
          const nodeName = Object.keys(chunk)[0];
          const nodeState = chunk[nodeName];
          socket.emit('node_complete', { node: nodeName, state: nodeState, session_id: sessionId });
          if (nodeState.outputType && nodeState.outputRef) {
            socket.emit('coding_result', { outputType: nodeState.outputType, outputRef: nodeState.outputRef, pendingDiffId: nodeState.pendingDiffId });
          }
        }
      } catch {
        // Fallback: use legacy agent_query path
        socket.emit('log', { message: '[System] Coding agent not yet available, using legacy path.' });
      } finally {
        emitRegistry.unregister(sessionId);
        emitRegistry.register(sessionId, (event, evData) => socket.emit(event as string, evData));
      }
    });

    // ── Legacy agent_query (kept for backward compat) ────────────────────────
    socket.on('agent_query', async (data: { query: string; repo_url: string }) => {
      // Auto-load workspace if not already loaded
      if (!currentWorkspacePath) {
        const result = await resolveWorkspace(data.repo_url);
        if ('error' in result) { socket.emit('error', { message: result.error }); return; }
        currentWorkspacePath = result.workspacePath;
      }

      // Delegate to coding_query with no selection (whole repo context)
      socket.emit('coding_query' as any, { query: data.query, selectedNodeIds: [], task: 'explain' });
      socket.emit('log', { message: '[System] Routing through legacy agent_query path.' });

      try {
        const { graph: codingGraph } = await import('./src/orchestration/coding_graph.ts');
        const llmConfigRef = store.put(sessionLLMConfig, 3600);

        emitRegistry.register(sessionId, (event, evData) => socket.emit(event as string, evData));

        const stream = await codingGraph.stream({
          userQuery: data.query,
          repoPath: currentWorkspacePath,
          sessionId,
          llmConfigRef,
          graphRef: sessionGraphRef,
          task: 'explain' as const,
        });

        for await (const chunk of stream) {
          const nodeName = Object.keys(chunk)[0];
          const nodeState = chunk[nodeName];
          socket.emit('node_complete', { node: nodeName, state: nodeState, session_id: sessionId });
        }
      } catch (error: unknown) {
        socket.emit('error', { message: error instanceof Error ? error.message : String(error) });
      } finally {
        emitRegistry.unregister(sessionId);
      }
    });

    // ── LLM config update ────────────────────────────────────────────────────
    socket.on('set_llm_config', async (data: { config: LLMConfig }) => {
      try {
        const { getLLM } = await import('./src/infrastructure/llm_factory.ts');
        const llm = getLLM(data.config);
        await (llm as any).invoke([{ role: 'user', content: 'ping' }]);
        sessionLLMConfig = data.config;
        socket.emit('llm_config_ack', { config: data.config, valid: true });
      } catch (error: unknown) {
        socket.emit('llm_config_ack', { config: data.config, valid: false, error: error instanceof Error ? error.message : String(error) });
      }
    });

    // ── File content (on bubble/node click) ──────────────────────────────────
    socket.on('request_file', (data: { path: string }) => {
      if (!currentWorkspacePath) { socket.emit('file_content_result', { path: data.path, error: 'No workspace loaded.' }); return; }
      try {
        const fullPath = path.resolve(path.join(currentWorkspacePath, data.path));
        const workspaceBase = path.resolve(path.join(process.cwd(), 'workspace'));
        const isInWorkspace = fullPath.startsWith(workspaceBase) || fullPath.startsWith(path.resolve(currentWorkspacePath));
        if (!isInWorkspace) { socket.emit('file_content_result', { path: data.path, error: 'Access denied.' }); return; }
        socket.emit('file_content_result', { path: data.path, content: fs.readFileSync(fullPath, 'utf-8') });
      } catch (error: unknown) {
        socket.emit('file_content_result', { path: data.path, error: error instanceof Error ? error.message : String(error) });
      }
    });

    // ── Apply diff ───────────────────────────────────────────────────────────
    socket.on('apply_diff', (data: { diffId: string }) => {
      try {
        const stored = store.get(data.diffId) as { files: { original: string; modified: string; appliedBlocks: number; filePath: string | null }[] } | null;
        if (!stored) { socket.emit('diff_applied', { success: false, message: 'Diff expired or not found.' }); return; }

        let totalBlocks = 0;
        const written: string[] = [];
        for (const f of stored.files) {
          if (!f.filePath) continue;
          fs.writeFileSync(f.filePath, f.modified, 'utf-8');
          totalBlocks += f.appliedBlocks;
          written.push(path.basename(f.filePath));
        }
        if (written.length === 0) { socket.emit('diff_applied', { success: false, message: 'No files had a valid path.' }); return; }
        socket.emit('diff_applied', { success: true, message: `Applied ${totalBlocks} change(s) across ${written.join(', ')}` });
      } catch (error: unknown) {
        socket.emit('diff_applied', { success: false, message: error instanceof Error ? error.message : String(error) });
      }
    });

    socket.on('disconnect', () => {
      emitRegistry.unregister(sessionId);
      console.log('Client disconnected:', sessionId);
    });
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({ server: { middlewareMode: true }, appType: 'spa' });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req: any, res: any) => res.sendFile(path.join(distPath, 'index.html')));
  }

  httpServer.listen(PORT, '0.0.0.0', () => console.log(`Entiendo running at http://localhost:${PORT}`));
}

startServer();
