import React, { useEffect, useRef, useState } from 'react';
import { Layout, GitBranch, BookOpen, FlaskConical, GitMerge, Activity, Copy, Check, Download } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import mermaid from 'mermaid';
import DiffViewer from './DiffViewer.tsx';
import FileViewer from './FileViewer.tsx';

export interface FileDiff {
  filePath: string | null;
  original: string;
  modified: string;
  appliedBlocks: number;
}

interface AnalysisResult {
  type: string;
  content: string;
  node?: string;
}

interface OutputPanelProps {
  analysisResult: AnalysisResult | null;
  streamingContent: string | null;
  diffData: FileDiff[] | null;
  fileView: { path: string; content: string } | null;
  activeNode: string | null;
  isProcessing: boolean;
  onAcceptDiff: () => void;
  onRejectDiff: () => void;
  onCloseFile: () => void;
}

const NODE_META: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  diagram:          { label: 'Diagram',      icon: GitBranch,    color: 'text-violet-400' },
  micro_logic:      { label: 'Flow Diagram', icon: GitBranch,    color: 'text-violet-400' },
  macro_structure:  { label: 'Architecture', icon: Layout,       color: 'text-indigo-400' },
  deep_explanation: { label: 'Explanation',  icon: BookOpen,     color: 'text-sky-400'    },
  test:             { label: 'Tests',        icon: FlaskConical, color: 'text-emerald-400'},
  refactor:         { label: 'Refactor',     icon: GitMerge,     color: 'text-amber-400'  },
};

function MermaidRenderer({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!ref.current || !chart) return;
    mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose', darkMode: true });
    mermaid
      .render(`mermaid-${Math.random().toString(36).slice(2, 9)}`, chart)
      .then(({ svg }) => { if (ref.current) ref.current.innerHTML = svg; })
      .catch(err => console.error('Mermaid render error:', err));
  }, [chart]);

  const handleExport = () => {
    const svg = ref.current?.innerHTML;
    if (!svg) return;
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'diagram.svg';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(chart);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col gap-3">
      <div ref={ref} className="w-full flex justify-center py-4 bg-slate-900/60 border border-white/5 rounded-xl overflow-hidden" />
      <div className="flex justify-end gap-2">
        <button onClick={handleCopy} className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-slate-400 hover:text-slate-200 text-[10px] font-medium rounded-lg transition-all">
          {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy source'}
        </button>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-2.5 py-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/20 text-indigo-400 text-[10px] font-medium rounded-lg transition-all">
          <Download className="w-3 h-3" /> Export SVG
        </button>
      </div>
    </div>
  );
}

function MarkdownRenderer({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="flex justify-end flex-shrink-0">
        <button onClick={handleCopy} className="flex items-center gap-1 px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-500 hover:text-slate-300 text-[9px] transition-all">
          {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <div className="prose prose-invert prose-xs max-w-none flex-1">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 px-6 text-center">
      <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
        <Activity className="w-6 h-6 text-indigo-400" />
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-300">Ready to analyse</p>
        <p className="text-[11px] text-slate-600 mt-1">Results will appear here after you send a query</p>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full mt-2">
        {[
          ['Architecture', 'Show dependency graph'],
          ['Explain', 'How does the auth flow work?'],
          ['Diagram', 'Draw a class diagram'],
          ['Tests', 'Generate tests for utils.ts'],
        ].map(([label, hint]) => (
          <div key={label} className="flex flex-col gap-0.5 p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-left">
            <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-widest">{label}</span>
            <span className="text-[10px] text-slate-500">{hint}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function OutputPanel({
  analysisResult, streamingContent, diffData, fileView,
  activeNode, isProcessing,
  onAcceptDiff, onRejectDiff, onCloseFile,
}: OutputPanelProps) {
  const meta = NODE_META[analysisResult?.node ?? activeNode ?? ''] ?? { label: 'Output', icon: Layout, color: 'text-indigo-400' };
  const Icon = meta.icon;

  const panelKey = fileView ? 'file'
    : diffData ? 'diff'
    : analysisResult ? `result-${analysisResult.node}-${analysisResult.type}`
    : streamingContent ? 'streaming'
    : 'empty';

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={panelKey}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.2 }}
        className="flex-1 bg-white/[0.04] backdrop-blur-2xl border border-white/10 rounded-2xl overflow-hidden flex flex-col shadow-2xl min-h-0"
      >
        {fileView ? (
          <FileViewer path={fileView.path} content={fileView.content} onClose={onCloseFile} />
        ) : diffData ? (
          <>
            <div className="px-4 py-3 border-b border-white/5 bg-white/5 flex items-center gap-2 flex-shrink-0">
              <GitMerge className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Refactor</span>
              <span className="ml-auto text-[9px] font-mono text-slate-600 px-1.5 py-0.5 bg-white/5 rounded">diff_proposal</span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <DiffViewer diffs={diffData} onAccept={onAcceptDiff} onReject={onRejectDiff} />
            </div>
          </>
        ) : (analysisResult || streamingContent) ? (
          <>
            {/* Smart header */}
            <div className="px-4 py-3 border-b border-white/5 bg-white/5 flex items-center gap-2 flex-shrink-0">
              <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${meta.color}`} />
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                {streamingContent && !analysisResult ? (
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
                    Streaming
                  </span>
                ) : meta.label}
              </span>
              {analysisResult?.type && (
                <span className="ml-auto text-[9px] font-mono text-slate-600 px-1.5 py-0.5 bg-white/5 rounded">{analysisResult.type}</span>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-4 text-xs leading-relaxed text-slate-300">
              {analysisResult?.type === 'mermaid' ? (
                <MermaidRenderer chart={analysisResult.content} />
              ) : (
                <MarkdownRenderer content={analysisResult?.content ?? streamingContent ?? ''} />
              )}
            </div>
          </>
        ) : (
          <EmptyState />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
