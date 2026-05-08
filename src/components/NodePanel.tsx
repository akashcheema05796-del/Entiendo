import React, { useState } from 'react';
import { X, FileCode, Layout } from 'lucide-react';
import { GraphNode } from '../types/project_graph.ts';
import { CodingTask } from '../types/selection_context.ts';
import NodeInspector from './NodeInspector.tsx';
import ActionBar from './ActionBar.tsx';
import ResultView from './ResultView.tsx';
import DiffViewer from './DiffViewer.tsx';

interface CodingResult {
  outputType: string;
  content: string;
  pendingDiffId?: string | null;
}

interface NodePanelProps {
  selectedNodes: GraphNode[];
  isProcessing: boolean;
  codingResult: CodingResult | null;
  fileView: { path: string; content: string } | null;
  onAction: (task: CodingTask, query?: string) => void;
  onClose: () => void;
  onAcceptDiff: () => void;
  onRejectDiff: () => void;
  onSymbolClick: (node: GraphNode, symbolName: string) => void;
  onCloseFile: () => void;
}

export default function NodePanel({
  selectedNodes, isProcessing, codingResult, fileView,
  onAction, onClose, onAcceptDiff, onRejectDiff, onSymbolClick, onCloseFile,
}: NodePanelProps) {
  const [activeTab, setActiveTab] = useState<'inspector' | 'result'>('inspector');

  // Switch to result tab automatically when result arrives
  React.useEffect(() => {
    if (codingResult) setActiveTab('result');
  }, [codingResult]);

  return (
    <div className="flex flex-col h-full bg-[#0d0f14]/95 border-l border-white/5">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-white/3 flex-shrink-0">
        <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
          <Layout className="w-3.5 h-3.5 text-indigo-400" />
          {selectedNodes.length === 0 ? 'Node Inspector' : selectedNodes.length === 1 ? selectedNodes[0].label : `${selectedNodes.length} nodes`}
        </div>
        <button onClick={onClose} className="text-slate-600 hover:text-slate-300 transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Tabs */}
      {codingResult && (
        <div className="flex border-b border-white/5 flex-shrink-0">
          {(['inspector', 'result'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                activeTab === tab ? 'text-indigo-400 border-b-2 border-indigo-500' : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              {tab === 'inspector' ? 'Inspector' : 'Result'}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {fileView ? (
          <div className="flex flex-col h-full">
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 bg-white/3 flex-shrink-0">
              <div className="flex items-center gap-2 text-[9px] text-slate-400 font-mono">
                <FileCode className="w-3 h-3 text-indigo-400" />
                {fileView.path}
              </div>
              <button onClick={onCloseFile} className="text-slate-600 hover:text-slate-300">
                <X className="w-3 h-3" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <pre className="text-[10px] font-mono text-slate-300 whitespace-pre-wrap break-all leading-relaxed">
                {fileView.content}
              </pre>
            </div>
          </div>
        ) : activeTab === 'result' && codingResult ? (
          <div className="p-4">
            <ResultView
              outputType={codingResult.outputType}
              content={codingResult.content}
              pendingDiffId={codingResult.pendingDiffId}
              onAcceptDiff={onAcceptDiff}
              onRejectDiff={onRejectDiff}
            />
          </div>
        ) : (
          <div className="p-4 flex flex-col gap-4">
            <NodeInspector nodes={selectedNodes} onSymbolClick={onSymbolClick} />
            <ActionBar
              selectedCount={selectedNodes.length}
              onAction={onAction}
              disabled={isProcessing}
            />
          </div>
        )}
      </div>
    </div>
  );
}
