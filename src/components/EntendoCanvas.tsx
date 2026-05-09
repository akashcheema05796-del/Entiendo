import React, { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { Code, Share2, PanelRight, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { GoogleGenAI } from '@google/genai';
import BubbleCanvas, { Bubble } from './BubbleCanvas.tsx';
import OutputPanel, { FileDiff } from './OutputPanel.tsx';
import QueryInput, { ChatEntry } from './QueryInput.tsx';
import Telemetry, { LogEntry } from './Telemetry.tsx';

const TERMINAL_NODES = new Set(['micro_logic', 'macro_structure', 'diagram', 'deep_explanation', 'refactor', 'test', 'error_handler']);

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

function makeBubble(id: string, x: number, y: number, size: number, color: string, label: string, filePath?: string, type: Bubble['type'] = 'agent'): Bubble {
  return {
    id, x, y, size, color, label, filePath, type,
    driftX: (Math.random() - 0.5) * 60,
    driftY: (Math.random() - 0.5) * 60,
    driftDuration: Math.random() * 6 + 5,
  };
}

function makeLog(message: string): LogEntry {
  return { message, time: Date.now() };
}

export default function EntendoCanvas() {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [query, setQuery] = useState('');
  const [repoUrl, setRepoUrl] = useState('anthropics/financial-services');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [analysisResult, setAnalysisResult] = useState<{ type: string; content: string; node?: string } | null>(null);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [diffData, setDiffData] = useState<FileDiff[] | null>(null);
  const [pendingDiffId, setPendingDiffId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isCloning, setIsCloning] = useState(false);
  const [showPanel, setShowPanel] = useState(false);
  const [fileView, setFileView] = useState<{ path: string; content: string } | null>(null);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatEntry[]>([]);
  const socketRef = useRef<Socket | null>(null);
  const lastQueryRef = useRef('');

  useEffect(() => {
    const initialBubbles = Array.from({ length: 20 }).map((_, i) =>
      makeBubble(
        `init-${i}`,
        Math.random() * window.innerWidth,
        Math.random() * window.innerHeight,
        Math.random() * 40 + 20,
        COLORS[Math.floor(Math.random() * COLORS.length)],
        `sys_node_${i}.bin`,
      )
    );
    setBubbles(initialBubbles);

    const socket = io();
    socketRef.current = socket;

    socket.on('clone_start', () => {
      setIsCloning(true);
      setLogs(prev => [...prev, makeLog('[System] Cloning repository...')]);
    });

    socket.on('clone_done', () => {
      setIsCloning(false);
      setLogs(prev => [...prev, makeLog('[System] Clone complete.')]);
    });

    socket.on('log', (data: { message: string }) => {
      setLogs(prev => [...prev, makeLog(data.message)]);
    });

    socket.on('token', (data: { token: string }) => {
      setStreamingContent(prev => (prev ?? '') + data.token);
      setShowPanel(true);
    });

    socket.on('repo_structure', (data: { tree: { name: string; path: string; size: number }[]; repo_url: string }) => {
      setLogs(prev => [...prev, makeLog(`[System] Visualizing ${data.tree.length} artifacts...`)]);
      const newBubbles = data.tree.slice(0, 60).map((file, i) => {
        const isCode = /\.(ts|tsx|js|jsx|py|go|rs)$/.test(file.name);
        const isDoc = /\.(md|txt)$/.test(file.name);
        const color = isCode ? '#6366f1' : isDoc ? '#10b981' : file.name.includes('.') ? '#94a3b8' : '#f59e0b';
        const size = Math.min(Math.log(file.size + 1) * 4 + 20, 80);
        return makeBubble(
          `file-${i}`,
          Math.random() * (window.innerWidth - 100) + 50,
          Math.random() * (window.innerHeight - 200) + 100,
          size, color, file.name, file.path,
          file.name.includes('.') ? 'file' : 'folder',
        );
      });
      setBubbles(newBubbles);
      performClientAnalysis(data.tree, data.repo_url);
    });

    socket.on('node_complete', (data: { node: string; state: { outputType?: string; outputRef?: string; pendingDiffId?: string } }) => {
      setLogs(prev => [...prev, makeLog(`--- [${data.node}] ✓`)]);
      setActiveNode(data.node);

      if (data.state.outputType === 'diff_proposal' && data.state.outputRef) {
        try {
          const parsed = JSON.parse(data.state.outputRef);
          const diffs: FileDiff[] = Array.isArray(parsed) ? parsed : [parsed];
          setDiffData(diffs);
          setPendingDiffId(data.state.pendingDiffId ?? null);
          setAnalysisResult(null);
          setStreamingContent(null);
          setShowPanel(true);
        } catch {
          setAnalysisResult({ type: 'markdown', content: data.state.outputRef, node: data.node });
        }
      } else if (data.state.outputType && data.state.outputRef) {
        const result = { type: data.state.outputType, content: data.state.outputRef, node: data.node };
        setAnalysisResult(result);
        setStreamingContent(null);
        setDiffData(null);
        setShowPanel(true);

        // Save to chat history
        if (lastQueryRef.current) {
          setChatHistory(prev => [...prev, {
            id: `${Date.now()}-${data.node}`,
            query: lastQueryRef.current,
            node: data.node,
            timestamp: Date.now(),
          }]);
        }
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
        setLogs(prev => [...prev, makeLog(`[Error] Could not open ${data.path}: ${data.error}`)]);
      }
    });

    socket.on('diff_applied', (data: { success: boolean; message: string }) => {
      setLogs(prev => [...prev, makeLog(data.success ? `✓ ${data.message}` : `[Error] ${data.message}`)]);
      setDiffData(null);
      setPendingDiffId(null);
    });

    socket.on('error', (data: { message: string }) => {
      setLogs(prev => [...prev, makeLog(`[Critical Error] ${data.message}`)]);
      setIsProcessing(false);
      setIsCloning(false);
    });

    return () => { socket.disconnect(); };
  }, []);

  const handleSend = () => {
    if (!query.trim() || !socketRef.current) return;
    lastQueryRef.current = query;
    setIsProcessing(true);
    setAnalysisResult(null);
    setStreamingContent(null);
    setDiffData(null);
    setFileView(null);
    setLogs(prev => [...prev, makeLog(`>>> ${query}`)]);
    socketRef.current.emit('agent_query', { query, repo_url: repoUrl });
    setQuery('');
  };

  const handleBubbleClick = (bubble: Bubble) => {
    if (bubble.type !== 'file' || !bubble.filePath) return;
    setLogs(prev => [...prev, makeLog(`[System] Opening ${bubble.label}...`)]);
    socketRef.current?.emit('request_file', { path: bubble.filePath });
  };

  const handleAcceptDiff = () => {
    if (!pendingDiffId) return;
    socketRef.current?.emit('apply_diff', { diffId: pendingDiffId });
  };

  const handleRejectDiff = () => {
    setDiffData(null);
    setPendingDiffId(null);
    setLogs(prev => [...prev, makeLog('[Refactor] Changes rejected.')]);
  };

  const handleHistoryClick = (entry: ChatEntry) => {
    setQuery(entry.query);
  };

  const performClientAnalysis = async (tree: { path: string }[], url: string) => {
    const apiKey = import.meta.env.VITE_GEMINI_API_KEY as string | undefined;
    if (!apiKey) return;
    try {
      setLogs(prev => [...prev, makeLog('[Inference] Bootstrapping reasoning model...')]);
      const ai = new GoogleGenAI({ apiKey });
      const fileList = tree.slice(0, 80).map(f => f.path).join('\n');
      const prompt = `Analyze this repo structure for ${url}.\nFiles:\n${fileList}\n\nReturn Markdown with:\n1. 2-sentence architecture summary.\n2. Tech stack (comma-separated).\n3. 3 key logical domains.`;
      const response = await ai.models.generateContent({ model: 'gemini-1.5-flash', contents: prompt });
      setAnalysisResult({ type: 'markdown', content: response.text ?? '', node: 'macro_structure' });
      setShowPanel(true);
      setLogs(prev => [...prev, makeLog('[Inference] ✓ Contextual summary generated.')]);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLogs(prev => [...prev, makeLog(`[System] LLM error: ${message}`)]);
    }
  };

  return (
    <div className="relative w-full h-screen bg-[#0a0c10] overflow-hidden font-sans text-slate-100">
      {/* Background */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-slate-900 via-[#0a0c10] to-[#0a0c10]" />

      {/* Bubble canvas */}
      <BubbleCanvas bubbles={bubbles} onBubbleClick={handleBubbleClick} />

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
              <p className="text-[9px] text-slate-500 font-mono tracking-widest uppercase">Vibe_to_Visual_Coding</p>
            </div>
          </div>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          <div className="hidden sm:flex items-center gap-3 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 focus-within:ring-2 focus-within:ring-indigo-500/50 transition-all">
            <Code className="w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="github-owner/repo"
              className="bg-transparent border-none outline-none text-[11px] font-mono w-48 sm:w-64 text-slate-300 placeholder:text-slate-600"
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
          <button
            onClick={() => setShowPanel(p => !p)}
            className="lg:hidden p-2 bg-white/5 border border-white/10 rounded-xl text-slate-400 hover:text-white transition-all"
          >
            <PanelRight className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Right panel */}
      <AnimatePresence>
        {(showPanel || (typeof window !== 'undefined' && window.innerWidth >= 1024)) && (
          <motion.div
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="absolute right-0 top-16 bottom-0 w-full sm:w-[420px] lg:w-[450px] flex flex-col gap-3 z-30 p-3 sm:p-4"
          >
            <button
              onClick={() => setShowPanel(false)}
              className="lg:hidden self-end p-1.5 bg-white/5 border border-white/10 rounded-lg text-slate-500 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>

            <OutputPanel
              analysisResult={analysisResult}
              streamingContent={streamingContent}
              diffData={diffData}
              fileView={fileView}
              activeNode={activeNode}
              isProcessing={isProcessing}
              onAcceptDiff={handleAcceptDiff}
              onRejectDiff={handleRejectDiff}
              onCloseFile={() => setFileView(null)}
            />

            <div className="flex-shrink-0">
              <Telemetry logs={logs} isProcessing={isProcessing || isCloning} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input HUD */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 sm:px-6 z-40">
        <QueryInput
          query={query}
          isProcessing={isProcessing}
          isCloning={isCloning}
          chatHistory={chatHistory}
          onQueryChange={setQuery}
          onSend={handleSend}
          onHistoryClick={handleHistoryClick}
        />
      </div>
    </div>
  );
}
