import React, { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { Send, MessageSquare, Code, Layout, Zap, Box, Share2, PanelRight, X, FileCode } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { GoogleGenAI } from '@google/genai';
import ReactMarkdown from 'react-markdown';
import mermaid from 'mermaid';
import DiffViewer, { FileDiff } from './DiffViewer.tsx';

/**
 * EntendoCanvas.tsx
 * The Interactive Visualization Layer.
 */

interface Bubble {
  id: string;
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
  filePath?: string;
  type: 'file' | 'folder' | 'agent';
}

interface DiffData {
  files: FileDiff[];
}

const Mermaid = ({ chart }: { chart: string }) => {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current && chart) {
      mermaid.initialize({ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' });
      mermaid
        .render(`mermaid-${Math.random().toString(36).substr(2, 9)}`, chart)
        .then(({ svg }) => { if (ref.current) ref.current.innerHTML = svg; })
        .catch(err => console.error('Mermaid render error:', err));
    }
  }, [chart]);
  return <div ref={ref} className="w-full flex justify-center py-4 bg-white rounded-xl overflow-hidden shadow-inner" />;
};

const TERMINAL_NODES = new Set(['micro_logic', 'macro_structure', 'deep_explanation', 'refactor', 'error_handler']);

export default function EntendoCanvas() {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [query, setQuery] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [analysisResult, setAnalysisResult] = useState<{ type: string; content: string } | null>(null);
  const [diffData, setDiffData] = useState<DiffData | null>(null);
  const [pendingDiffId, setPendingDiffId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isCloning, setIsCloning] = useState(false);
  const [showPanel, setShowPanel] = useState(false);
  const [fileView, setFileView] = useState<{ path: string; content: string } | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  useEffect(() => {
    const initialBubbles = Array.from({ length: 20 }).map((_, i) => ({
      id: `init-${i}`,
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      size: Math.random() * 40 + 20,
      color: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'][Math.floor(Math.random() * 5)],
      label: `sys_node_${i}.bin`,
      type: 'agent' as const,
    }));
    setBubbles(initialBubbles);

    const socket = io();
    socketRef.current = socket;

    socket.on('clone_start', () => {
      setIsCloning(true);
      setLogs(prev => [...prev, '[System] Cloning repository...']);
    });

    socket.on('clone_done', () => {
      setIsCloning(false);
      setLogs(prev => [...prev, '[System] Clone complete.']);
    });

    socket.on('log', (data: { message: string }) => {
      setLogs(prev => [...prev, data.message]);
    });

    socket.on('tool_call', (data: { tool: string; args: Record<string, unknown>; iteration: number }) => {
      const argStr = Object.values(data.args).map(v => `"${String(v).slice(0, 40)}"`).join(', ');
      setLogs(prev => [...prev, `[Agent:${data.iteration}] → ${data.tool}(${argStr})`]);
    });

    socket.on('tool_result', (data: { tool: string; preview: string }) => {
      setLogs(prev => [...prev, `[Agent] ← ${data.tool}: ${data.preview}`]);
    });

    socket.on('repo_structure', (data: { tree: { name: string; path: string; size: number }[]; repo_url: string }) => {
      setLogs(prev => [...prev, `[System] Visualizing ${data.tree.length} artifacts...`]);
      const newBubbles = data.tree.slice(0, 60).map((file, i) => {
        const isCode = /\.(ts|tsx|js|jsx|py|go|rs)$/.test(file.name);
        const isDoc = /\.(md|txt)$/.test(file.name);
        return {
          id: `file-${i}`,
          x: Math.random() * (window.innerWidth - 100) + 50,
          y: Math.random() * (window.innerHeight - 200) + 100,
          size: Math.min(Math.log(file.size + 1) * 4 + 20, 80),
          color: isCode ? '#6366f1' : isDoc ? '#10b981' : file.name.includes('.') ? '#94a3b8' : '#f59e0b',
          label: file.name,
          filePath: file.path,
          type: (file.name.includes('.') ? 'file' : 'folder') as Bubble['type'],
        };
      });
      setBubbles(newBubbles);
      performClientAnalysis(data.tree, data.repo_url);
    });

    socket.on('node_complete', (data: { node: string; state: { outputType?: string; outputRef?: string; pendingDiffId?: string } }) => {
      setLogs(prev => [...prev, `[Node: ${data.node}] → ${(Math.random() * 200 + 100).toFixed(0)}ms`]);

      if (data.state.outputType === 'diff_proposal' && data.state.outputRef) {
        try {
          const parsed: DiffData = JSON.parse(data.state.outputRef);
          setDiffData(parsed);
          setPendingDiffId(data.state.pendingDiffId ?? null);
          setAnalysisResult(null);
          setShowPanel(true);
        } catch {
          setAnalysisResult({ type: 'markdown', content: data.state.outputRef });
        }
      } else if (data.state.outputType && data.state.outputRef) {
        setAnalysisResult({ type: data.state.outputType, content: data.state.outputRef });
        setDiffData(null);
        setShowPanel(true);
      }

      if (TERMINAL_NODES.has(data.node)) setIsProcessing(false);
    });

    socket.on('file_content_result', (data: { path: string; content?: string; error?: string }) => {
      if (data.content !== undefined) {
        setFileView({ path: data.path, content: data.content });
        setAnalysisResult(null);
        setDiffData(null);
        setShowPanel(true);
      } else {
        setLogs(prev => [...prev, `[Error] Could not open ${data.path}: ${data.error}`]);
      }
    });

    socket.on('diff_applied', (data: { success: boolean; message: string }) => {
      setLogs(prev => [...prev, data.success ? `[Refactor] ✓ ${data.message}` : `[Refactor] ✗ ${data.message}`]);
      setDiffData(null);
      setPendingDiffId(null);
    });

    socket.on('error', (data: { message: string }) => {
      setLogs(prev => [...prev, `[Critical Error] ${data.message}`]);
      setIsProcessing(false);
      setIsCloning(false);
    });

    const animate = () => {
      setBubbles(prev => prev.map(b => ({
        ...b,
        x: b.x + (Math.random() - 0.5) * 0.8,
        y: b.y + (Math.random() - 0.5) * 0.8,
      })));
      requestAnimationFrame(animate);
    };
    const req = requestAnimationFrame(animate);

    return () => { cancelAnimationFrame(req); socket.disconnect(); };
  }, []);

  const handleSend = () => {
    if (!query.trim() || !repoUrl.trim() || !socketRef.current) return;
    setIsProcessing(true);
    setAnalysisResult(null);
    setDiffData(null);
    setFileView(null);
    setLogs(prev => [...prev, `>>> ${query}`]);
    socketRef.current.emit('agent_query', { query, repo_url: repoUrl });
    setQuery('');
  };

  const handleBubbleClick = (bubble: Bubble) => {
    if (bubble.type !== 'file' || !bubble.filePath) return;
    setLogs(prev => [...prev, `[System] Opening ${bubble.label}...`]);
    socketRef.current?.emit('request_file', { path: bubble.filePath });
  };

  const handleAcceptDiff = () => {
    if (!pendingDiffId) return;
    socketRef.current?.emit('apply_diff', { diffId: pendingDiffId });
  };

  const handleRejectDiff = () => {
    setDiffData(null);
    setPendingDiffId(null);
    setLogs(prev => [...prev, '[Refactor] Changes rejected.']);
  };

  const performClientAnalysis = async (tree: { path: string }[], url: string) => {
    const apiKey = import.meta.env.VITE_GEMINI_API_KEY as string | undefined;
    if (!apiKey) {
      setLogs(prev => [...prev, '[System] VITE_GEMINI_API_KEY not set — skipping client analysis.']);
      return;
    }
    try {
      setLogs(prev => [...prev, '[Inference] Bootstrapping reasoning model...']);
      const ai = new GoogleGenAI({ apiKey });
      const fileList = tree.slice(0, 80).map(f => f.path).join('\n');
      const prompt = `Analyze this repo structure for ${url}.\nFiles:\n${fileList}\n\nReturn Markdown with:\n1. 2-sentence architecture summary.\n2. Tech stack (comma-separated).\n3. 3 key logical domains.`;
      const response = await ai.models.generateContent({ model: 'gemini-2.5-flash', contents: prompt });
      setAnalysisResult({ type: 'markdown', content: response.text ?? '' });
      setShowPanel(true);
      setLogs(prev => [...prev, '[Inference] Contextual summary generated.']);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLogs(prev => [...prev, `[System] LLM error: ${message}`]);
    }
  };

  const panelContent = fileView ? (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-white/5">
        <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
          <FileCode className="w-3.5 h-3.5 text-indigo-400" />
          {fileView.path}
        </div>
        <button onClick={() => setFileView(null)} className="text-slate-500 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <pre className="text-[10px] font-mono text-slate-300 whitespace-pre-wrap break-all leading-relaxed">
          {fileView.content}
        </pre>
      </div>
    </div>
  ) : diffData ? (
    <div className="p-6">
      <DiffViewer
        files={diffData.files}
        onAccept={handleAcceptDiff}
        onReject={handleRejectDiff}
      />
    </div>
  ) : analysisResult ? (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-white/5 bg-white/5 flex justify-between items-center">
        <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
          <Layout className="w-3.5 h-3.5 text-indigo-400" />
          Inferred_Architecture
        </div>
        <div className="text-[9px] font-mono text-slate-500 px-2 py-0.5 bg-white/5 rounded uppercase">
          {analysisResult.type}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-6 text-xs leading-relaxed text-slate-300">
        {analysisResult.type === 'mermaid' ? (
          <Mermaid chart={analysisResult.content} />
        ) : (
          <div className="prose prose-invert prose-xs max-w-none">
            <ReactMarkdown>{analysisResult.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  ) : null;

  return (
    <div className="relative w-full h-screen bg-[#0a0c10] overflow-hidden font-sans text-slate-100">
      {/* Background */}
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
              animate={{ x: bubble.x, y: bubble.y, scale: 1, opacity: 0.8, transition: { type: 'spring', stiffness: 50, damping: 20 } }}
              exit={{ scale: 0, opacity: 0 }}
              onClick={() => handleBubbleClick(bubble)}
              className="absolute rounded-full border flex items-center justify-center backdrop-blur-sm shadow-lg pointer-events-auto cursor-pointer"
              style={{ width: bubble.size, height: bubble.size, left: 0, top: 0, backgroundColor: `${bubble.color}11`, borderColor: `${bubble.color}44`, boxShadow: `0 0 30px ${bubble.color}22` }}
              whileHover={{ scale: 1.2, backgroundColor: `${bubble.color}33`, borderColor: `${bubble.color}aa`, zIndex: 50 }}
              title={bubble.filePath ?? bubble.label}
            >
              <div className="flex flex-col items-center gap-1 overflow-hidden px-2">
                {bubble.type === 'file'
                  ? <Box className="w-3 h-3" style={{ color: bubble.color }} />
                  : <Zap className="w-3 h-3" style={{ color: bubble.color }} />}
                <span className="text-[7px] font-mono font-bold text-slate-300 truncate w-full text-center">{bubble.label}</span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Connection Lines */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-10">
        {bubbles.slice(0, 15).map((b, i) =>
          bubbles[i + 1] && (
            <line key={i} x1={b.x} y1={b.y} x2={bubbles[i + 1].x} y2={bubbles[i + 1].y} stroke={b.color} strokeWidth="0.5" />
          )
        )}
      </svg>

      {/* Header */}
      <header className="absolute top-0 left-0 right-0 h-16 px-4 sm:px-8 flex justify-between items-center bg-[#0a0c10]/40 backdrop-blur-xl border-b border-white/5 z-40">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center text-white font-black shadow-lg shadow-indigo-500/20 rotate-3">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-black tracking-tighter text-white">
                ENTIENDO <span className="text-indigo-400 font-medium">V4</span>
              </h1>
              <p className="text-[9px] text-slate-500 font-mono tracking-widest uppercase">Neural_Architecture_Scanner</p>
            </div>
          </div>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          <div className="hidden sm:flex items-center gap-3 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 focus-within:ring-2 focus-within:ring-indigo-500/50 transition-all">
            <Code className="w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="owner/repo, github URL, or /local/path"
              className="bg-transparent border-none outline-none text-[11px] font-mono w-48 sm:w-72 text-slate-300 placeholder:text-slate-600"
              value={repoUrl}
              onChange={e => setRepoUrl(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          {(isCloning || isProcessing) && (
            <div className="flex items-center gap-2 text-[10px] text-amber-400 font-mono animate-pulse">
              <span className="w-1.5 h-1.5 bg-amber-400 rounded-full" />
              {isCloning ? 'CLONING...' : 'PROCESSING...'}
            </div>
          )}
          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-indigo-500/10 text-indigo-400 text-[10px] font-bold rounded-full border border-indigo-500/20">
            <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse shadow-[0_0_8px_#6366f1]" />
            REASONING_CLUSTER: ON
          </div>
          {/* Mobile panel toggle */}
          <button
            onClick={() => setShowPanel(p => !p)}
            className="lg:hidden p-2 bg-white/5 border border-white/10 rounded-xl text-slate-400 hover:text-white transition-all"
          >
            <PanelRight className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Output Panel — right side on desktop, slide-up on mobile */}
      <AnimatePresence>
        {(showPanel || typeof window !== 'undefined' && window.innerWidth >= 1024) && (
          <motion.div
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="absolute right-0 top-16 bottom-0 w-full sm:w-[420px] lg:w-[450px] flex flex-col gap-3 z-30 p-3 sm:p-4"
          >
            {/* Close button on mobile */}
            <button
              onClick={() => setShowPanel(false)}
              className="lg:hidden self-end p-1.5 bg-white/5 border border-white/10 rounded-lg text-slate-500 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>

            {/* Main content panel */}
            <AnimatePresence mode="wait">
              {panelContent && (
                <motion.div
                  key={fileView ? 'file' : diffData ? 'diff' : 'analysis'}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="flex-1 bg-white/5 backdrop-blur-2xl border border-white/10 rounded-2xl overflow-hidden flex flex-col shadow-2xl min-h-0"
                >
                  {panelContent}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Telemetry */}
            <div className="h-44 bg-[#0a0c10]/80 border border-white/10 rounded-2xl p-4 font-mono flex flex-col shadow-xl flex-shrink-0">
              <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">System_Telemetry</span>
                <div className="flex gap-1">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="w-1 h-3 bg-indigo-500/40 rounded-full animate-pulse" style={{ animationDelay: `${i * 0.2}s` }} />
                  ))}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto space-y-1.5 scrollbar-hide">
                {logs.map((log, i) => (
                  <div key={i} className={`text-[10px] flex items-start gap-2 ${log.startsWith('>>>') ? 'text-indigo-400' : log.includes('Error') ? 'text-red-400' : log.includes('✓') ? 'text-green-400' : 'text-slate-500'}`}>
                    <span className="opacity-30 flex-shrink-0">[{new Date().toLocaleTimeString()}]</span>
                    <span className="flex-1 leading-tight">{log}</span>
                  </div>
                ))}
                <div ref={logsEndRef} />
                {(isProcessing || isCloning) && (
                  <div className="flex items-center gap-2 text-indigo-400 text-[10px] animate-pulse">
                    <span>&gt;</span>
                    <span className="font-bold">{isCloning ? 'CLONING_REPO...' : 'TRAVERSING_GRAPH_SPACE...'}</span>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input HUD */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 sm:px-6 z-40">
        <div className="p-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-[22px] shadow-2xl shadow-indigo-500/20">
          <div className="bg-[#0a0c10] rounded-[20px] p-2 flex items-center gap-3">
            <div className="pl-3">
              <MessageSquare className="w-5 h-5 text-slate-500" />
            </div>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder="Explain the orchestration layer..."
              className="flex-1 bg-transparent py-3 text-sm font-medium text-white outline-none placeholder:text-slate-600"
            />
            <button
              onClick={handleSend}
              disabled={isProcessing || isCloning || !query.trim() || !repoUrl.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 text-white p-3 rounded-2xl transition-all shadow-lg active:scale-95 group"
            >
              <Send className="w-5 h-5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
