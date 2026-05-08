import React from 'react';
import { GraphNode } from '../types/project_graph.ts';
import { FileCode, Folder, Code, GitBranch } from 'lucide-react';

interface NodeInspectorProps {
  nodes: GraphNode[];
  onSymbolClick?: (node: GraphNode, symbolName: string) => void;
}

const KIND_ICONS: Record<string, React.ReactNode> = {
  file: <FileCode className="w-3 h-3 text-indigo-400" />,
  directory: <Folder className="w-3 h-3 text-amber-400" />,
  function: <Code className="w-3 h-3 text-green-400" />,
  class: <GitBranch className="w-3 h-3 text-purple-400" />,
};

const LANG_BADGE: Record<string, string> = {
  typescript: 'bg-indigo-500/20 text-indigo-300',
  javascript: 'bg-yellow-500/20 text-yellow-300',
  python:     'bg-yellow-500/20 text-yellow-300',
  go:         'bg-cyan-500/20 text-cyan-300',
  rust:       'bg-red-500/20 text-red-300',
  markdown:   'bg-green-500/20 text-green-300',
};

export default function NodeInspector({ nodes, onSymbolClick }: NodeInspectorProps) {
  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-slate-600 text-[11px] font-mono gap-2">
        <span>Click a node to inspect it</span>
        <span className="text-[9px]">Shift+click to multi-select</span>
      </div>
    );
  }

  if (nodes.length > 1) {
    const totalLoc = nodes.reduce((n, nd) => n + nd.loc, 0);
    return (
      <div className="flex flex-col gap-2 text-[11px]">
        <div className="text-slate-400 font-mono">{nodes.length} nodes selected</div>
        <div className="text-slate-500">{totalLoc.toLocaleString()} total lines of code</div>
        <div className="flex flex-wrap gap-1 mt-1">
          {nodes.slice(0, 8).map(n => (
            <span key={n.id} className="px-2 py-0.5 bg-white/5 border border-white/10 rounded text-[9px] font-mono text-slate-400">
              {n.label}
            </span>
          ))}
          {nodes.length > 8 && <span className="text-[9px] text-slate-600">+{nodes.length - 8} more</span>}
        </div>
      </div>
    );
  }

  const node = nodes[0];
  const badgeClass = LANG_BADGE[node.language] ?? 'bg-slate-500/20 text-slate-400';

  return (
    <div className="flex flex-col gap-3 text-[11px]">
      {/* Header */}
      <div className="flex items-center gap-2">
        {KIND_ICONS[node.kind] ?? <FileCode className="w-3 h-3 text-slate-400" />}
        <span className="font-mono text-white font-bold truncate">{node.label}</span>
        <span className={`ml-auto px-1.5 py-0.5 rounded text-[9px] font-bold ${badgeClass}`}>
          {node.language}
        </span>
      </div>

      {/* Path */}
      <div className="text-slate-500 font-mono text-[9px] break-all">{node.relativePath}</div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-white/5 rounded-lg p-2">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider">Lines</div>
          <div className="text-white font-bold">{node.loc.toLocaleString()}</div>
        </div>
        <div className="bg-white/5 rounded-lg p-2">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider">Symbols</div>
          <div className="text-white font-bold">{node.symbols.length}</div>
        </div>
      </div>

      {/* Symbol list */}
      {node.symbols.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold">Symbols</div>
          <div className="max-h-32 overflow-y-auto flex flex-col gap-0.5">
            {node.symbols.map((sym, i) => (
              <button
                key={i}
                onClick={() => onSymbolClick?.(node, sym.name)}
                className="flex items-center gap-2 px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-left transition-colors group"
              >
                <span className={`text-[8px] font-bold px-1 rounded ${
                  sym.kind === 'function' ? 'bg-green-500/20 text-green-400' :
                  sym.kind === 'class' ? 'bg-purple-500/20 text-purple-400' :
                  sym.kind === 'interface' ? 'bg-blue-500/20 text-blue-400' :
                  'bg-slate-500/20 text-slate-400'
                }`}>{sym.kind[0].toUpperCase()}</span>
                <span className="font-mono text-slate-300 group-hover:text-white text-[10px]">{sym.name}</span>
                <span className="ml-auto text-[8px] text-slate-600">:{sym.startLine}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
