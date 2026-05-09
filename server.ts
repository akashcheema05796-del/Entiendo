import express from 'express';
import 'dotenv/config';
import { createServer } from 'http';
import { Server } from 'socket.io';
import path from 'path';
import fs from 'fs';
import { createServer as createViteServer } from 'vite';
import { graph } from './src/orchestration/graph.ts';
import { store } from './src/infrastructure/session_store.ts';
import { ragIndexer } from './src/tools/rag_indexer.ts';
import { graphIndexer } from './src/tools/graph_indexer.ts';
import { tokenEmitter } from './src/infrastructure/token_emitter.ts';
import { execSync } from 'child_process';

// Per-session conversation history
const conversationHistory = new Map<string, { role: string; content: string }[]>();

/**
 * server.ts
 * The Transport Layer using Express + Socket.io.
 */

function getFileTree(dir: string, baseDir: string = dir): { name: string; path: string; size: number }[] {
  let results: { name: string; path: string; size: number }[] = [];
  try {
    const list = fs.readdirSync(dir);
    list.forEach((file) => {
      const filePath = path.join(dir, file);
      const stat = fs.statSync(filePath);
      if (stat && stat.isDirectory()) {
        if (!['node_modules', '.git', 'dist', '__pycache__'].includes(file)) {
          results = results.concat(getFileTree(filePath, baseDir));
        }
      } else {
        results.push({ name: file, path: path.relative(baseDir, filePath), size: stat.size });
      }
    });
  } catch (e: unknown) {
    console.error('Error reading tree:', e);
  }
  return results;
}

async function startServer() {
  const app = express();
  const httpServer = createServer(app);
  const io = new Server(httpServer, { cors: { origin: '*' } });

  const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;

  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);

    // Per-connection mutable state
    let currentWorkspacePath: string | null = null;
    const sessionId = socket.id;

    // Forward streamed LLM tokens to this socket
    const onToken = (token: string) => socket.emit('token', { token });
    tokenEmitter.on(sessionId, onToken);

    socket.on('agent_query', async (data: { query: string; repo_url: string }) => {
      const workspacePath = path.join(
        process.cwd(),
        'workspace',
        data.repo_url.replace(/\//g, '_')
      );
      currentWorkspacePath = workspacePath;

      try {
        const workspaceDir = path.join(process.cwd(), 'workspace');
        if (!fs.existsSync(workspaceDir)) fs.mkdirSync(workspaceDir, { recursive: true });

        // Clone repo if not cached
        if (!fs.existsSync(workspacePath)) {
          socket.emit('clone_start', { repo_url: data.repo_url });
          console.log(`Cloning ${data.repo_url}...`);
          await new Promise<void>((resolve, reject) => {
            const { spawn } = require('child_process');
            const proc = spawn('npx', ['-y', 'degit', data.repo_url, workspacePath, '--force'], {
              timeout: 60_000,
              stdio: 'pipe',
            });
            proc.on('close', (code: number) => {
              if (code === 0) resolve();
              else reject(new Error(`degit exited with code ${code}`));
            });
            proc.on('error', reject);
          });
          socket.emit('clone_done', { repo_url: data.repo_url });
        }

        // Send file tree for visualization
        const fileTree = getFileTree(workspacePath);
        socket.emit('repo_structure', { tree: fileTree, repo_url: data.repo_url });

        // Kick off RAG + knowledge graph indexing in parallel (non-blocking)
        ragIndexer.indexRepo(workspacePath, sessionId, (msg) => {
          socket.emit('log', { message: msg });
        }).catch(() => {});

        graphIndexer.indexRepo(workspacePath, sessionId, (msg) => {
          socket.emit('log', { message: msg });
        }).catch(() => {});

        // Read recent git diff for context
        let gitDiff: string | null = null;
        try {
          gitDiff = execSync('git log --oneline -5 && git diff HEAD~1 HEAD --stat', {
            cwd: workspacePath,
            timeout: 5000,
          }).toString().trim();
        } catch { /* repo may have only one commit */ }

        // Load and update conversation history
        const history = conversationHistory.get(sessionId) ?? [];
        history.push({ role: 'user', content: data.query });
        conversationHistory.set(sessionId, history.slice(-20));

        // Run LangGraph
        const stream = await graph.stream({
          userQuery: data.query,
          repoPath: workspacePath,
          sessionId,
          conversationHistory: JSON.stringify(history),
          gitDiff,
        });

        let lastOutput = '';
        for await (const chunk of stream) {
          const nodeName = Object.keys(chunk)[0];
          const nodeState = chunk[nodeName];
          if (nodeState.outputRef) lastOutput = nodeState.outputRef;
          socket.emit('node_complete', { node: nodeName, state: nodeState, session_id: sessionId });
        }

        // Append assistant response to conversation history
        if (lastOutput) {
          const updated = conversationHistory.get(sessionId) ?? [];
          updated.push({ role: 'assistant', content: lastOutput.slice(0, 500) });
          conversationHistory.set(sessionId, updated.slice(-20));
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        socket.emit('error', { message });
      }
    });

    // Serve raw file content when a bubble is clicked
    socket.on('request_file', (data: { path: string }) => {
      if (!currentWorkspacePath) {
        socket.emit('file_content_result', { path: data.path, error: 'No repo loaded yet.' });
        return;
      }
      try {
        const fullPath = path.resolve(path.join(currentWorkspacePath, data.path));
        // Security: prevent path traversal outside workspace
        if (!fullPath.startsWith(path.resolve(path.join(process.cwd(), 'workspace')))) {
          socket.emit('file_content_result', { path: data.path, error: 'Access denied.' });
          return;
        }
        const content = fs.readFileSync(fullPath, 'utf-8');
        socket.emit('file_content_result', { path: data.path, content });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        socket.emit('file_content_result', { path: data.path, error: message });
      }
    });

    // Apply an accepted diff to disk
    socket.on('apply_diff', (data: { diffId: string }) => {
      try {
        const payload = store.get(data.diffId) as
          | { filePath: string; modified: string; appliedBlocks: number }[]
          | { filePath: string | null; modified: string; appliedBlocks: number }
          | null;

        if (!payload) {
          socket.emit('diff_applied', { success: false, message: 'Diff expired or not found.' });
          return;
        }

        // Normalise to array (backwards-compat with old single-file shape)
        const diffs = Array.isArray(payload) ? payload : [payload];
        let totalBlocks = 0;
        const written: string[] = [];

        for (const diff of diffs) {
          if (!diff.filePath) continue;
          fs.writeFileSync(diff.filePath, diff.modified, 'utf-8');
          totalBlocks += diff.appliedBlocks;
          written.push(path.basename(diff.filePath));
        }

        if (written.length === 0) {
          socket.emit('diff_applied', { success: false, message: 'No target files in diff.' });
          return;
        }

        socket.emit('diff_applied', {
          success: true,
          message: `Applied ${totalBlocks} change(s) across ${written.join(', ')}`,
        });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        socket.emit('diff_applied', { success: false, message });
      }
    });

    socket.on('disconnect', () => {
      tokenEmitter.off(sessionId, onToken);
      conversationHistory.delete(sessionId);
      console.log('Client disconnected:', sessionId);
    });
  });

  // Health check for Railway / load balancers
  app.get('/health', (_req, res) => res.json({ status: 'ok' }));

  // Vite / static serving
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({ server: { middlewareMode: true }, appType: 'spa' });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => res.sendFile(path.join(distPath, 'index.html')));
  }

  httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 Entiendo running at http://localhost:${PORT}`);
  });
}

startServer();
