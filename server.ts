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

  const PORT = 3000;

  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);

    // Per-connection mutable state
    let currentWorkspacePath: string | null = null;
    const sessionId = socket.id;

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
          const { execSync } = await import('child_process');
          execSync(`npx -y degit ${data.repo_url} ${workspacePath} --force`, { timeout: 60_000 });
          socket.emit('clone_done', { repo_url: data.repo_url });
        }

        // Send file tree for visualization
        const fileTree = getFileTree(workspacePath);
        socket.emit('repo_structure', { tree: fileTree, repo_url: data.repo_url });

        // Kick off RAG indexing in the background (non-blocking)
        ragIndexer.indexRepo(workspacePath, sessionId, (msg) => {
          socket.emit('log', { message: msg });
        }).catch(() => {});

        // Run LangGraph
        const stream = await graph.stream({
          userQuery: data.query,
          repoPath: workspacePath,
          sessionId,
        });

        for await (const chunk of stream) {
          const nodeName = Object.keys(chunk)[0];
          const nodeState = chunk[nodeName];
          socket.emit('node_complete', { node: nodeName, state: nodeState, session_id: sessionId });
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
        const diff = store.get(data.diffId) as {
          original: string;
          modified: string;
          appliedBlocks: number;
          filePath: string | null;
        } | null;

        if (!diff) {
          socket.emit('diff_applied', { success: false, message: 'Diff expired or not found.' });
          return;
        }
        if (!diff.filePath) {
          socket.emit('diff_applied', { success: false, message: 'No target file in this diff.' });
          return;
        }

        fs.writeFileSync(diff.filePath, diff.modified, 'utf-8');
        socket.emit('diff_applied', {
          success: true,
          message: `Applied ${diff.appliedBlocks} change(s) to ${path.basename(diff.filePath)}`,
        });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        socket.emit('diff_applied', { success: false, message });
      }
    });

    socket.on('disconnect', () => {
      console.log('Client disconnected:', sessionId);
    });
  });

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
