import React, { useState, useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { Share2, Code, Settings, RefreshCw } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { GraphNode, ProjectGraph } from '../types/project_graph.ts';
import { LLMConfig, getDefaultLLMConfig } from '../types/llm_config.ts';
import { CodingTask } from '../types/selection_context.ts';
import GraphCanvas from './GraphCanvas.tsx';
import NodePanel from './NodePanel.tsx';
import TelemetryLog from './TelemetryLog.tsx';
import QueryInput from './QueryInput.tsx';
import LLMSettingsPanel from './LLMSettingsPanel.tsx';

interface CodingResult {
  outputType: string;
  content: string;
  pendingDiffId?: string | null;
}

export default function ProjectGraphView() {
  const socketRef = useRef<Socket | null>(null);

  // Workspace
  const [repoInput, setRepoInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);

  // Graph
  const [graphData, setGraphData] = useState<ProjectGraph | null>(null);
  const [indexPct, setIndexPct] = useState(0);
  const [indexPhase, setIndexPhase] = useState('');

  // Selection
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(new Set());
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());

  // Panel
  const [showPanel, setShowPanel] = useState(false);
  const [fileView, setFileView] = useState<{ path: string; content: string } | null>(null);
  const [codingResult, setCodingResult] = useState<CodingResult | null>(null);
  const [pendingDiffId, setPendingDiffId] = useState<string | null>(null);

  // LLM
  const [llmConfig, setLlmConfig] = useState<LLMConfig>(getDefaultLLMConfig());
  const [showLLMSettings, setShowLLMSettings] = useState(false);

  // Processing
  const [isProcessing, setIsProcessing] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  // Canvas size
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 1200, height: 700 });

  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      const e = entries[0];
      setCanvasSize({ width: e.contentRect.width, height: e.contentRect.height });
    });
    if (canvasRef.current) obs.observe(canvasRef.current);
    return () => obs.disconnect();
  }, []);

  const addLog = (msg: string) => setLogs(prev => [...prev.slice(-200), msg]);

  // Socket setup
  useEffect(() => {
    const socket = io();
    socketRef.current = socket;

    socket.on('log', (d: { message: string }) => addLog(d.message));
    socket.on('tool_call', (d: { tool: string; args: Record<string, unknown>; iteration: number }) => {
      const argStr = Object.values(d.args).map(v => `"${String(v).slice(0, 40)}"`).join(', ');
      addLog(`[Agent:${d.iteration}] → ${d.tool}(${argStr})`);
    });
    socket.on('tool_result', (d: { tool: string; preview: string }) => addLog(`[Agent] ← ${d.tool}: ${d.preview}`));

    socket.on('graph_progress', (d: { phase: string; pct: number; detail?: string }) => {
      setIndexPct(d.pct);
      setIndexPhase(d.detail ?? d.phase);
      addLog(`[Graph] ${d.detail ?? d.phase}`);
    });

    socket.on('graph_ready', (d: { nodeCount: number; edgeCount: number; cached?: boolean }) => {
      setIsIndexing(false);
      setIsLoading(false);
      addLog(`[Graph] Ready — ${d.nodeCount} nodes, ${d.edgeCount} edges${d.cached ? ' (cached)' : ''}`);
    });

    socket.on('graph_data', (data: ProjectGraph) => {
      setGraphData(data);
      setShowPanel(false);
    });

    socket.on('node_expanded', (d: { nodeId: string; childNodes: GraphNode[]; childEdges: any[] }) => {
      setExpandedNodeIds(prev => new Set([...prev, d.nodeId]));
      setGraphData(prev => {
        if (!prev) return prev;
        const existingIds = new Set(prev.nodes.map(n => n.id));
        const newNodes = d.childNodes.filter(n => !existingIds.has(n.id));
        const existingEdgeIds = new Set(prev.edges.map(e => e.id));
        const newEdges = d.childEdges.filter((e: any) => !existingEdgeIds.has(e.id));
        return { ...prev, nodes: [...prev.nodes, ...newNodes], edges: [...prev.edges, ...newEdges] };
      });
    });

    socket.on('coding_result', (d: { outputType: string; outputRef: string; pendingDiffId?: string }) => {
      setCodingResult({ outputType: d.outputType, content: d.outputRef, pendingDiffId: d.pendingDiffId });
      setPendingDiffId(d.pendingDiffId ?? null);
      setShowPanel(true);
      setIsProcessing(false);
    });

    socket.on('node_complete', (d: { node: string; state: any }) => {
      addLog(`[Node: ${d.node}] complete`);
      if (d.state?.outputType && d.state?.outputRef) {
        setCodingResult({ outputType: d.state.outputType, content: d.state.outputRef, pendingDiffId: d.state.pendingDiffId });
        setPendingDiffId(d.state.pendingDiffId ?? null);
        setShowPanel(true);
      }
    });

    socket.on('file_content_result', (d: { path: string; content?: string; error?: string }) => {
      if (d.content !== undefined) {
        setFileView({ path: d.path, content: d.content });
        setShowPanel(true);
      } else {
        addLog(`[Error] ${d.path}: ${d.error}`);
      }
    });

    socket.on('diff_applied', (d: { success: boolean; message: string }) => {
      addLog(d.success ? `[Refactor] ✓ ${d.message}` : `[Refactor] ✗ ${d.message}`);
      setCodingResult(null);
      setPendingDiffId(null);
    });

    socket.on('llm_config_ack', (d: { valid: boolean; error?: string }) => {
      addLog(d.valid ? '[LLM] Connection OK' : `[LLM] Failed: ${d.error}`);
    });

    socket.on('error', (d: { message: string }) => {
      addLog(`[Error] ${d.message}`);
      setIsProcessing(false);
      setIsLoading(false);
      setIsIndexing(false);
    });

    return () => { socket.disconnect(); };
  }, []);

  const handleLoadWorkspace = () => {
    if (!repoInput.trim() || !socketRef.current) return;
    setIsLoading(true);
    setIsIndexing(true);
    setIndexPct(0);
    setGraphData(null);
    setSelectedNodeIds(new Set());
    setCodingResult(null);
    addLog(`>>> Loading: ${repoInput}`);
    socketRef.current.emit('load_workspace', { path: repoInput.trim() });
  };

  const handleNodeClick = (nodeId: string, multi: boolean) => {
    setSelectedNodeIds(prev => {
      const next = new Set(multi ? prev : []);
      if (prev.has(nodeId) && !multi) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
    setShowPanel(true);
    setFileView(null);
  };

  const handleNodeDoubleClick = (node: GraphNode) => {
    if (node.kind === 'file' && !expandedNodeIds.has(node.id)) {
      socketRef.current?.emit('expand_node', { nodeId: node.id });
      addLog(`[Graph] Expanding ${node.label}...`);
    } else if (node.kind === 'file') {
      socketRef.current?.emit('request_file', { path: node.relativePath });
    } else if (node.kind === 'directory') {
      socketRef.current?.emit('expand_directory', { relativePath: node.relativePath });
    }
  };

  const handleAction = (task: CodingTask, query?: string) => {
    if (!socketRef.current) return;
    const q = query ?? `${task.replace('_', ' ')} the selected code`;
    setIsProcessing(true);
    setCodingResult(null);
    addLog(`>>> ${task}: ${q}`);
    socketRef.current.emit('coding_query', {
      query: q,
      selectedNodeIds: Array.from(selectedNodeIds),
      task,
    });
  };

  const handleQuerySubmit = (query: string, task: CodingTask) => {
    handleAction(task, query);
  };

  const handleAcceptDiff = () => {
    if (pendingDiffId) socketRef.current?.emit('apply_diff', { diffId: pendingDiffId });
  };

  const handleRejectDiff = () => {
    setCodingResult(null);
    setPendingDiffId(null);
    addLog('[Refactor] Changes rejected.');
  };

  const handleSaveLLMConfig = (config: LLMConfig) => {
    setLlmConfig(config);
    socketRef.current?.emit('set_llm_config', { config });
    setShowLLMSettings(false);
  };

  const selectedNodes = graphData?.nodes.filter(n => selectedNodeIds.has(n.id)) ?? [];

  return (
    <div className="relative w-full h-screen bg-[#0a0c10] overflow-hidden font-sans text-slate-100 flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 h-14 px-4 flex items-center justify-between bg-[#0a0c10]/80 backdrop-blur-xl border-b border-white/5 z-40">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-xl flex items-center justify-center text-white font-black shadow-lg shadow-indigo-500/20 rotate-3">
              <Share2 className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-sm font-black tracking-tighter text-white">ENTIENDO <span className="text-indigo-400 font-medium">V5</span></h1>
              <p className="text-[8px] text-slate-500 font-mono tracking-widest uppercase">Visual_Coding_Agent</p>
            </div>
          </div>

          <div className="h-5 w-px bg-white/10" />

          {/* Repo input */}
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-3 py-1.5 focus-within:ring-2 focus-within:ring-indigo-500/50 transition-all">
            <Code className="w-3 h-3 text-slate-500" />
            <input
              type="text"
              placeholder="owner/repo, URL, or /local/path"
              className="bg-transparent border-none outline-none text-[11px] font-mono w-56 text-slate-300 placeholder:text-slate-600"
              value={repoInput}
              onChange={e => setRepoInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLoadWorkspace()}
            />
            <button
              onClick={handleLoadWorkspace}
              disabled={!repoInput.trim() || isLoading}
              className="text-[9px] font-bold px-2.5 py-0.5 bg-indigo-600/80 hover:bg-indigo-600 disabled:opacity-40 text-white rounded-full transition-all"
            >
              {isLoading ? 'Loading…' : 'Load'}
            </button>
          </div>
        </div>

        {/* Right header controls */}
        <div className="flex items-center gap-2">
          {isIndexing && (
            <div className="flex items-center gap-2 text-[10px] text-cyan-400 font-mono">
              <RefreshCw className="w-3 h-3 animate-spin" />
              {indexPhase} {indexPct > 0 && `${indexPct}%`}
            </div>
          )}
          {isProcessing && (
            <div className="flex items-center gap-2 text-[10px] text-amber-400 font-mono animate-pulse">
              <span className="w-1.5 h-1.5 bg-amber-400 rounded-full" />
              PROCESSING...
            </div>
          )}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-indigo-500/10 text-indigo-400 text-[9px] font-bold rounded-full border border-indigo-500/20">
            <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse shadow-[0_0_8px_#6366f1]" />
            {llmConfig.provider.toUpperCase()}:{llmConfig.model.split('-')[0].toUpperCase()}
          </div>
          <button
            onClick={() => setShowLLMSettings(true)}
            className="p-1.5 bg-white/5 border border-white/10 rounded-xl text-slate-400 hover:text-white transition-all"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main layout */}
      <div className="flex flex-1 min-h-0">
        {/* Graph canvas */}
        <div ref={canvasRef} className="flex-1 relative min-w-0" onClick={() => setSelectedNodeIds(new Set())}>
          {!graphData ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-600 gap-4">
              <Share2 className="w-12 h-12 opacity-20" />
              <div className="text-center">
                <div className="text-sm font-bold text-slate-500">No project loaded</div>
                <div className="text-[11px] text-slate-700 mt-1">Enter a repo URL or local path above and press Load</div>
              </div>
            </div>
          ) : (
            <GraphCanvas
              graph={graphData}
              selectedNodeIds={selectedNodeIds}
              onNodeClick={handleNodeClick}
              onNodeDoubleClick={handleNodeDoubleClick}
              width={canvasSize.width}
              height={canvasSize.height}
            />
          )}
        </div>

        {/* Right panel */}
        <AnimatePresence>
          {showPanel && (
            <motion.div
              initial={{ x: '100%', opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: '100%', opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="w-[420px] flex-shrink-0 border-l border-white/5 flex flex-col"
            >
              <NodePanel
                selectedNodes={selectedNodes}
                isProcessing={isProcessing}
                codingResult={codingResult}
                fileView={fileView}
                onAction={handleAction}
                onClose={() => setShowPanel(false)}
                onAcceptDiff={handleAcceptDiff}
                onRejectDiff={handleRejectDiff}
                onSymbolClick={(node, sym) => {
                  socketRef.current?.emit('expand_node', { nodeId: node.id });
                  addLog(`[Graph] Expanding symbol: ${sym}`);
                }}
                onCloseFile={() => setFileView(null)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Bottom bar: telemetry + query input */}
      <div className="flex-shrink-0 px-4 pb-4 pt-2 flex flex-col gap-2 border-t border-white/5 bg-[#0a0c10]/80 backdrop-blur-xl z-20">
        <TelemetryLog logs={logs} isProcessing={isProcessing} />
        <QueryInput
          onSubmit={handleQuerySubmit}
          disabled={isProcessing || isLoading}
          selectedCount={selectedNodeIds.size}
        />
      </div>

      {/* LLM settings overlay */}
      <AnimatePresence>
        {showLLMSettings && (
          <LLMSettingsPanel
            current={llmConfig}
            onSave={handleSaveLLMConfig}
            onClose={() => setShowLLMSettings(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
