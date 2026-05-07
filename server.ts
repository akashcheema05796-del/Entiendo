import express from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { graph } from './src/orchestration/graph.ts';

/**
 * server.ts
 * The Transport Layer using Express + Socket.io.
 */

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

    socket.on('agent_query', async (data: { query: string, repo_path: string }) => {
      const sessionId = socket.id;
      
      try {
        const stream = await graph.stream({
          userQuery: data.query,
          repoPath: data.repo_path,
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
