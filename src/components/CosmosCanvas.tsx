import React, { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { Send, MessageSquare, Code, Layout, ShieldAlert } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

/**
 * CosmosCanvas.tsx
 * The Interactive Visualization Layer.
 * Renders floating bubbles representing the codebase.
 */

interface Bubble {
  id: string;
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
}

export default function CosmosCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [query, setQuery] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    // Initialize bubbles
    const initialBubbles = Array.from({ length: 15 }).map((_, i) => ({
      id: `file-${i}`,
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      size: Math.random() * 40 + 20,
      color: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'][Math.floor(Math.random() * 5)],
      label: `module_${i}.ts`
    }));
    setBubbles(initialBubbles);

    // Socket.io connection
    const socket = io();
    socketRef.current = socket;

    socket.on('node_complete', (data) => {
      setLogs(prev => [...prev, `[${data.node}] transition complete`]);
      if (data.node === 'micro_logic' || data.node === 'error') {
        setIsProcessing(false);
      }
    });

    socket.on('error', (data) => {
      setLogs(prev => [...prev, `Error: ${data.message}`]);
      setIsProcessing(false);
    });

    const animate = () => {
      setBubbles(prev => prev.map(b => ({
        ...b,
        x: b.x + (Math.random() - 0.5) * 0.5,
        y: b.y + (Math.random() - 0.5) * 0.5
      })));
      requestAnimationFrame(animate);
    };
    const req = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(req);
      socket.disconnect();
    };
  }, []);

  const handleSend = () => {
    if (!query.trim() || !socketRef.current) return;
    setIsProcessing(true);
    setLogs(prev => [...prev, `User: ${query}`]);
    socketRef.current.emit('agent_query', { query, repo_path: '.' });
    setQuery('');
  };

  return (
    <div className="relative w-full h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      {/* Background Stars/Canvas */}
      <canvas ref={canvasRef} className="absolute inset-0 opacity-40 pointer-events-none" />

      {/* Floating Bubbles (Simplified HTML representation for reactivity) */}
      <div className="absolute inset-0 pointer-events-none">
        {bubbles.map(bubble => (
          <motion.div
            key={bubble.id}
            initial={false}
            animate={{ x: bubble.x, y: bubble.y }}
            className="absolute rounded-full border border-slate-200 flex items-center justify-center bg-white/40 backdrop-blur-sm shadow-sm"
            style={{
              width: bubble.size,
              height: bubble.size,
              boxShadow: `0 0 20px ${bubble.color}22`,
              borderColor: `${bubble.color}44`
            }}
          >
            <span className="text-[8px] font-mono font-medium text-slate-600 truncate px-1">
              {bubble.label}
            </span>
          </motion.div>
        ))}
      </div>

      {/* Header - Bento Style */}
      <header className="absolute top-0 left-0 right-0 h-16 px-8 flex justify-between items-center bg-white/80 backdrop-blur-md border-b border-slate-200 z-20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold shadow-sm shadow-indigo-200">
            C
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-900">
              CODE_COSMOS / <span className="text-slate-500 font-medium">Universe Viz</span>
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1 bg-green-50 text-green-700 text-[10px] font-bold rounded-full border border-green-200">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            SYSTEM_ACTIVE
          </div>
          <button className="px-4 py-2 bg-slate-900 text-white text-xs font-semibold rounded-lg hover:bg-slate-800 transition-colors shadow-sm">
            Generate Analysis
          </button>
        </div>
      </header>

      {/* Main Agent Interface - Bento Card Style */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 z-30">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden flex flex-col max-h-[400px]">
          
          <div className="px-4 py-3 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
            <h2 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
              <MessageSquare className="w-3 h-3 text-indigo-600" />
              Strategic_Agent_Output
            </h2>
            <span className="text-[10px] text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
              V3.0 HYBRID
            </span>
          </div>

          {/* Logs / Stream */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-hide min-h-[150px]">
            {logs.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3 opacity-80 py-8">
                <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center">
                  <Layout className="w-6 h-6 text-slate-400" />
                </div>
                <p className="text-sm font-medium">Ask about your code, search flows, or refactor...</p>
              </div>
            )}
            {logs.map((log, i) => (
              <motion.div 
                key={i}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-xs font-mono text-slate-600 flex gap-3 items-start"
              >
                <div className="mt-1 w-1.5 h-1.5 rounded-full bg-slate-200 shrink-0" />
                <p className="flex-1 leading-relaxed">{log}</p>
              </motion.div>
            ))}
            {isProcessing && (
              <div className="flex items-center gap-3 text-indigo-600 text-[10px] font-bold uppercase tracking-widest pl-4.5">
                <div className="flex gap-1">
                  <span className="w-1 h-1 bg-current rounded-full animate-bounce" />
                  <span className="w-1 h-1 bg-current rounded-full animate-bounce [animation-delay:0.2s]" />
                  <span className="w-1 h-1 bg-current rounded-full animate-bounce [animation-delay:0.4s]" />
                </div>
                Routing_Inference...
              </div>
            )}
          </div>

          {/* Input Area */}
          <div className="p-4 bg-slate-50 border-t border-slate-200 flex gap-3">
            <input 
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder="e.g. Visualize the authentication flow..."
              className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all outline-none shadow-sm placeholder:text-slate-400"
            />
            <button 
              onClick={handleSend}
              disabled={isProcessing || !query.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white p-3 rounded-xl transition-all shadow-md shadow-indigo-100 flex items-center justify-center group active:scale-95"
            >
              <Send className="w-5 h-5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </button>
          </div>
        </div>
      </div>

      {/* Side HUDs - Bento Cards */}
      <div className="absolute top-24 right-8 w-64 space-y-6 z-20 hidden lg:block">
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="p-6 bg-white rounded-2xl border border-slate-200 shadow-sm"
        >
          <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">
            <Code className="w-4 h-4 text-indigo-600" />
            Active_Workspace
          </div>
          <div className="space-y-3">
            {['src/main.tsx', 'src/App.tsx', 'server.ts'].map(f => (
              <div key={f} className="flex items-center gap-3 group cursor-pointer">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-200 group-hover:bg-indigo-400 transition-colors" />
                <span className="text-[10px] font-mono font-medium text-slate-500 group-hover:text-slate-800 transition-colors">
                  {f}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-6 pt-4 border-t border-slate-100">
            <span className="text-[9px] px-2 py-1 bg-slate-50 rounded text-slate-400 font-mono uppercase tracking-tighter">
              #WORKDIR-LOCKED
            </span>
          </div>
        </motion.div>
        
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          className="p-6 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-100 text-white"
        >
           <div className="flex items-center gap-2 text-xs font-bold text-white/70 uppercase tracking-widest mb-3">
            <ShieldAlert className="w-4 h-4" />
            Privacy_Shield
          </div>
          <p className="text-[11px] leading-relaxed text-indigo-50 font-medium">
            Sensitive code remains local. Only classified intents are routed to reasoning clusters.
          </p>
          <div className="mt-4 flex items-center gap-2">
            <div className="h-1 flex-1 bg-white/20 rounded-full overflow-hidden">
              <div className="h-full bg-white w-full" />
            </div>
            <span className="text-[9px] font-bold">100% SECURE</span>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
