import express from 'express';
import 'dotenv/config';
import { createServer } from 'http';
import { Server } from 'socket.io';
import path from 'path';
import fs from 'fs';
import { createServer as createViteServer } from 'vite';
import { graph } from './src/orchestration/graph.ts';

/**
 * server.ts
 * The Transport Layer using Express + Socket.io.
 */

/**
 * Helper to get a flat list of files for visualization.
 */
function getFileTree(dir: string, baseDir: string = dir): any[] {
  let results: any[] = [];
  try {
    const list = fs.readdirSync(dir);
    list.forEach((file) => {
      const filePath = path.join(dir, file);
      const stat = fs.statSync(filePath);
      if (stat && stat.isDirectory()) {
        if (file !== 'node_modules' && file !== '.git' && file !== 'dist') {
          results = results.concat(getFileTree(filePath, baseDir));
        }
      } else {
        results.push({
          name: file,
          path: path.relative(baseDir, filePath),
          size: stat.size
        });
      }
    });
  } catch (e) {
    console.error('Error reading tree:', e);
  }
  return results;
}

async function startServer() {
  const app = express();
  const httpServer = createServer(app);
  const io = new Server(httpServer, {
    cors: { origin: '*' }
  });

  const PORT = 3000;

  // LangGraph Socket handler
  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);

    socket.on('agent_query', async (data: { query: string, repo_url: string }) => {
      const sessionId = socket.id;
      const workspacePath = path.join(process.cwd(), 'workspace', data.repo_url.replace(/\//g, '_'));
      
      try {
        // Ensure workspace directory exists
        if (!fs.existsSync(path.join(process.cwd(), 'workspace'))) {
            fs.mkdirSync(path.join(process.cwd(), 'workspace'));
        }

        // Clone if not exists
        if (!fs.existsSync(workspacePath)) {
            socket.emit('node_complete', { node: 'Ingestion', state: { outputType: 'markdown' }, session_id: sessionId });
            console.log(`Cloning ${data.repo_url} to ${workspacePath}...`);
            const { execSync } = await import('child_process');
            // Use --depth 1 for faster clones if it was git, but degit is already fast
            execSync(`npx -y degit ${data.repo_url} ${workspacePath} --force`);
        }

        // Get file tree for visualization
        const fileTree = getFileTree(workspacePath);
        socket.emit('repo_structure', { tree: fileTree, repo_url: data.repo_url });

        const stream = await graph.stream({
          userQuery: data.query,
          repoPath: workspacePath,
          sessionId: sessionId
        });

        for await (const chunk of stream) {
          const nodeName = Object.keys(chunk)[0];
          const nodeState = chunk[nodeName];

          socket.emit('node_complete', {
            node: nodeName,
            state: nodeState,
            session_id: sessionId
          });
        }
      } catch (error: any) {
        socket.emit('error', { message: error.message });
      }
    });

    socket.on('disconnect', () => {
      console.log('Client disconnected');
    });
  });

  // Vite integration
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 Code Cosmos running at http://localhost:${PORT}`);
  });
}

startServer();
