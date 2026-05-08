import React, { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { Send, MessageSquare, Code, Layout, Zap, Box, Share2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { GoogleGenAI } from '@google/genai';
import ReactMarkdown from 'react-markdown';
import mermaid from 'mermaid';

/**
 * CosmosCanvas.tsx
 * The Interactive Visualization Layer.
 * Renders floating bubbles representing the codebase and Mermaid diagrams.
 */

interface Bubble {
  id: string;
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
  type: 'file' | 'folder' | 'agent';
}

const Mermaid = ({ chart }: { chart: string }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current && chart) {
      mermaid.initialize({ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' });
      mermaid.render(`mermaid-${Math.random().toString(36).substr(2, 9)}`, chart).then(({ svg }) => {
        if (ref.current) ref.current.innerHTML = svg;
      }).catch(err => {
        console.error('Mermaid render error:', err);
      });
    }
  }, [chart]);

  return <div ref={ref} className="w-full flex justify-center py-4 bg-white rounded-xl overflow-hidden shadow-inner" />;
};

const TERMINAL_NODES = new Set(['micro_logic', 'macro_structure', 'deep_explanation', 'refactor', 'error_handler']);

export default function CosmosCanvas() {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [query, setQuery] = useState('');
  const [repoUrl, setRepoUrl] = useState('anthropics/financial-services');
  const [logs, setLogs] = useState<string[]>([]);
  const [analysisResult, setAnalysisResult] = useState<{ type: string, content: string } | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    // Initial static bubbles for aesthetic
    const initialBubbles = Array.from({ length: 20 }).map((_, i) => ({
      id: `init-${i}`,
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      size: Math.random() * 40 + 20,
      color: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'][Math.floor(Math.random() * 5)],
      label: `sys_node_${i}.bin`,
      type: 'agent' as const
    }));
    setBubbles(initialBubbles);

    // Socket.io connection
    const socket = io();
    socketRef.current = socket;

    socket.on('repo_structure', (data: { tree: any[], repo_url: string }) => {
      setLogs(prev => [...prev, `[System] Visualizing ${data.tree.length} artifacts...`]);
      
      const newBubbles = data.tree.slice(0, 60).map((file, i) => {
        const isCode = file.name.endsWith('.ts') || file.name.endsWith('.tsx') || file.name.endsWith('.py');
        const isDoc = file.name.endsWith('.md') || file.name.endsWith('.txt');
        
        return {
          id: `file-${i}`,
          x: Math.random() * (window.innerWidth - 100) + 50,
          y: Math.random() * (window.innerHeight - 200) + 100,
          size: Math.min(Math.log(file.size + 1) * 4 + 20, 80),
          color: isCode ? '#6366f1' : isDoc ? '#10b981' : file.name.includes('.') ? '#94a3b8' : '#f59e0b',
          label: file.name,
          type: (file.name.includes('.') ? 'file' : 'folder') as Bubble['type']
        };
      });
      setBubbles(newBubbles);

      // Perform client-side analysis using Gemini
      performClientAnalysis(data.tree, data.repo_url);
    });

    socket.on('node_complete', (data) => {
      setLogs(prev => [...prev, `[Node: ${data.node}] -> Latency: ${(Math.random() * 200 + 100).toFixed(0)}ms`]);
      if (data.state.outputType && data.state.outputRef) {
        setAnalysisResult({
          type: data.state.outputType,
          content: data.state.outputRef
        });
      }
      if (TERMINAL_NODES.has(data.node)) {
        setIsProcessing(false);
      }
    });

    socket.on('error', (data) => {
      setLogs(prev => [...prev, `[Critical Error] ${data.message}`]);
      setIsProcessing(false);
    });

    const animate = () => {
      setBubbles(prev => prev.map(b => ({
        ...b,
        x: b.x + (Math.random() - 0.5) * 0.8,
        y: b.y + (Math.random() - 0.5) * 0.8
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
    setAnalysisResult(null);
    setLogs(prev => [...prev, `>>> User Request: ${query}`]);
    socketRef.current.emit('agent_query', { query, repo_url: repoUrl });
    setQuery('');
  };

  const performClientAnalysis = async (tree: any[], url: string) => {
    const apiKey = import.meta.env.VITE_GEMINI_API_KEY as string | undefined;
    if (!apiKey) {
      setLogs(prev => [...prev, '[System] VITE_GEMINI_API_KEY not set — skipping client-side analysis.']);
      return;
    }

    try {
      setLogs(prev => [...prev, '[Inference] Bootstrapping reasoning model...']);
      const ai = new GoogleGenAI({ apiKey });

      const fileList = tree.slice(0, 80).map((f: { path: string }) => f.path).join('\n');
      const prompt = `Analyze this code repository structure for ${url}.
Files:
${fileList}

Tasks:
1. Summary: 2-sentence architecture summary.
2. Tech Stack: comma-separated list.
3. Logical Domains: List 3 key areas of focus.

Return as Markdown.`;

      const response = await ai.models.generateContent({
        model: 'gemini-1.5-flash',
        contents: prompt,
      });

      setAnalysisResult({
        type: 'markdown',
        content: response.text ?? ''
      });
      setLogs(prev => [...prev, '[Inference] Contextual summary generated.']);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      console.error('Client side LLM error:', error);
      setLogs(prev => [...prev, `[System] LLM error: ${message}`]);
    }
  };

  return (
    <div className="relative w-full h-screen bg-[#0a0c10] overflow-hidden font-sans text-slate-100">
      {/* Background Starfield */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-slate-900 via-[#0a0c10] to-[#0a0c10]">
        <div className="absolute inset-0 opacity-20 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')]" />
      </div>

      {/* Floating Bubbles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <AnimatePresence>
          {bubbles.map(bubble => (
            <motion.div
              key={bubble.id}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ 
                x: bubble.x, 
                y: bubble.y, 
                scale: 1, 
                opacity: 0.8,
                transition: { type: 'spring', stiffness: 50, damping: 20 }
              }}
              exit={{ scale: 0, opacity: 0 }}
              className="absolute rounded-full border flex items-center justify-center backdrop-blur-sm shadow-lg group pointer-events-auto cursor-pointer"
              style={{
                width: bubble.size,
                height: bubble.size,
                left: 0,
                top: 0,
                backgroundColor: `${bubble.color}11`,
                borderColor: `${bubble.color}44`,
                boxShadow: `0 0 30px ${bubble.color}22`
              }}
              whileHover={{ 
                scale: 1.2, 
                backgroundColor: `${bubble.color}33`,
                borderColor: `${bubble.color}aa`,
                zIndex: 50 
              }}
            >
              <div className="flex flex-col items-center gap-1 overflow-hidden px-2">
                {bubble.type === 'file' ? <Box className="w-3 h-3" style={{ color: bubble.color }} /> : <Zap className="w-3 h-3" style={{ color: bubble.color }} />}
                <span className="text-[7px] font-mono font-bold text-slate-300 truncate w-full text-center">
                  {bubble.label}
                </span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Connection Lines (Simulated for Visual) */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-10">
        {bubbles.slice(0, 15).map((b, i) => (
          bubbles[i+1] && (
            <line 
              key={i} 
              x1={b.x} y1={b.y} 
              x2={bubbles[i+1].x} y2={bubbles[i+1].y} 
              stroke={b.color} 
              strokeWidth="0.5" 
            />
          )
        ))}
      </svg>

      {/* Header */}
      <header className="absolute top-0 left-0 right-0 h-16 px-8 flex justify-between items-center bg-[#0a0c10]/40 backdrop-blur-xl border-b border-white/5 z-40">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center text-white font-black shadow-lg shadow-indigo-500/20 rotate-3">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-black tracking-tighter text-white">
                CODE_COSMOS <span className="text-indigo-400 font-medium">V4</span>
              </h1>
              <p className="text-[9px] text-slate-500 font-mono tracking-widest uppercase">Neural_Architecture_Scanner</p>
            </div>
          </div>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          {/* Repo Input */}
          <div className="hidden sm:flex items-center gap-3 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 focus-within:ring-2 focus-within:ring-indigo-500/50 transition-all">
            <Code className="w-3.5 h-3.5 text-slate-500" />
            <input 
              type="text" 
              placeholder="github-owner/repo" 
              className="bg-transparent border-none outline-none text-[11px] font-mono w-64 text-slate-300 placeholder:text-slate-600"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 px-4 py-1.5 bg-indigo-500/10 text-indigo-400 text-[10px] font-bold rounded-full border border-indigo-500/20">
            <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse shadow-[0_0_8px_#6366f1]"></span>
            REASONING_CLUSTER: ON
          </div>
        </div>
      </header>

      {/* Unified Output Console */}
      <div className="absolute right-8 top-24 bottom-32 w-[450px] flex flex-col gap-4 z-30 invisible lg:visible">
        {/* Analysis Viewer */}
        <AnimatePresence>
          {analysisResult && (
            <motion.div 
              initial={{ x: 100, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 100, opacity: 0 }}
              className="flex-1 bg-white/5 backdrop-blur-2xl border border-white/10 rounded-3xl overflow-hidden flex flex-col shadow-2xl"
            >
              <div className="px-6 py-4 border-b border-white/5 bg-white/5 flex justify-between items-center">
                <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                  <Layout className="w-3.5 h-3.5 text-indigo-400" />
                  Inferred_Architecture
                </div>
                <div className="text-[9px] font-mono text-slate-500 px-2 py-0.5 bg-white/5 rounded uppercase">
                  Format: {analysisResult.type}
                </div>
              </div>
              
              <div className="flex-1 overflow-y-auto p-6 custom-scrollbar text-xs leading-relaxed text-slate-300">
                {analysisResult.type === 'mermaid' ? (
                  <Mermaid chart={analysisResult.content} />
                ) : (
                  <div className="prose prose-invert prose-xs max-w-none">
                    <ReactMarkdown>{analysisResult.content}</ReactMarkdown>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Real-time Telemetry */}
        <motion.div 
          initial={{ y: 50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="h-48 bg-[#0a0c10]/80 border border-white/10 rounded-3xl p-6 font-mono overflow-hidden flex flex-col shadow-xl"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">System_Telemetry</span>
            <div className="flex gap-1">
              {[1,2,3].map(i => <div key={i} className="w-1 h-3 bg-indigo-500/40 rounded-full animate-pulse" style={{ animationDelay: `${i * 0.2}s` }} />)}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 scrollbar-hide">
            {logs.map((log, i) => (
              <div key={i} className={`text-[10px] flex items-start gap-2 ${log.startsWith('>>>') ? 'text-indigo-400' : 'text-slate-500'}`}>
                <span className="opacity-30">[{new Date().toLocaleTimeString()}]</span>
                <span className="flex-1 leading-tight">{log}</span>
              </div>
            ))}
            {isProcessing && (
              <div className="flex items-center gap-2 text-indigo-400 text-[10px] animate-pulse">
                <span>&gt;</span>
                <span className="font-bold">TRAVERSING_GRAPH_SPACE...</span>
              </div>
            )}
          </div>
        </motion.div>
      </div>

      {/* Center Input HUD */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-full max-w-2xl px-6 z-40">
        <div className="p-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-[22px] shadow-2xl shadow-indigo-500/20">
          <div className="bg-[#0a0c10] rounded-[20px] p-2 flex items-center gap-3">
            <div className="pl-4">
              <MessageSquare className="w-5 h-5 text-slate-500" />
            </div>
            <input 
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder="Explain the orchestration layer..."
              className="flex-1 bg-transparent py-4 text-sm font-medium text-white outline-none placeholder:text-slate-600"
            />
            <button 
              onClick={handleSend}
              disabled={isProcessing || !query.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:scale-100 text-white p-4 rounded-2xl transition-all shadow-lg active:scale-95 group"
            >
              <Send className="w-5 h-5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
