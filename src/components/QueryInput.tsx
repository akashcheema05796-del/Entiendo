import React from 'react';
import { Send, MessageSquare, GitBranch, BookOpen, FlaskConical, Layout, GitMerge } from 'lucide-react';

export interface ChatEntry {
  id: string;
  query: string;
  node: string;
  timestamp: number;
}

const QUICK_ACTIONS = [
  { icon: Layout,       label: 'Architecture', query: 'Show the project architecture overview' },
  { icon: GitBranch,    label: 'Dep graph',    query: 'Draw a dependency graph of the codebase' },
  { icon: BookOpen,     label: 'Explain',      query: 'Explain how the main data flow works' },
  { icon: FlaskConical, label: 'Tests',        query: 'Generate tests for the main module' },
  { icon: GitMerge,     label: 'Diagram',      query: 'Show a class diagram of the system' },
];

const NODE_COLORS: Record<string, string> = {
  diagram:          'bg-violet-500/15 text-violet-300 border-violet-500/20',
  micro_logic:      'bg-violet-500/15 text-violet-300 border-violet-500/20',
  macro_structure:  'bg-indigo-500/15 text-indigo-300 border-indigo-500/20',
  deep_explanation: 'bg-sky-500/15 text-sky-300 border-sky-500/20',
  test:             'bg-emerald-500/15 text-emerald-300 border-emerald-500/20',
  refactor:         'bg-amber-500/15 text-amber-300 border-amber-500/20',
};

interface QueryInputProps {
  query: string;
  isProcessing: boolean;
  isCloning: boolean;
  chatHistory: ChatEntry[];
  onQueryChange: (q: string) => void;
  onSend: () => void;
  onHistoryClick: (entry: ChatEntry) => void;
}

export default function QueryInput({
  query, isProcessing, isCloning, chatHistory,
  onQueryChange, onSend, onHistoryClick,
}: QueryInputProps) {
  const recentHistory = chatHistory.slice(-4).reverse();

  return (
    <div className="flex flex-col gap-2">
      {/* History chips */}
      {recentHistory.length > 0 && (
        <div className="flex gap-1.5 flex-wrap px-1">
          {recentHistory.map(entry => (
            <button
              key={entry.id}
              onClick={() => onHistoryClick(entry)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-medium transition-all hover:opacity-80 truncate max-w-[200px] ${NODE_COLORS[entry.node] ?? 'bg-white/5 text-slate-400 border-white/10'}`}
              title={entry.query}
            >
              <span className="truncate">{entry.query.slice(0, 35)}{entry.query.length > 35 ? '…' : ''}</span>
            </button>
          ))}
        </div>
      )}

      {/* Quick action chips — only shown when no history */}
      {recentHistory.length === 0 && (
        <div className="flex gap-1.5 flex-wrap px-1">
          {QUICK_ACTIONS.map(action => (
            <button
              key={action.label}
              onClick={() => onQueryChange(action.query)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/10 text-[10px] font-medium transition-all"
            >
              <action.icon className="w-3 h-3" />
              {action.label}
            </button>
          ))}
        </div>
      )}

      {/* Input bar */}
      <div className="p-[1px] bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-[22px] shadow-2xl shadow-indigo-500/20">
        <div className="bg-[#0a0c10] rounded-[20px] p-2 flex items-center gap-3">
          <div className="pl-3">
            <MessageSquare className="w-5 h-5 text-slate-500" />
          </div>
          <input
            type="text"
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && onSend()}
            placeholder="Vibe to visual coding..."
            className="flex-1 bg-transparent py-3 text-sm font-medium text-white outline-none placeholder:text-slate-600"
          />
          <button
            onClick={onSend}
            disabled={isProcessing || isCloning || !query.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 text-white p-3 rounded-2xl transition-all shadow-lg active:scale-95 group"
          >
            <Send className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </button>
        </div>
      </div>
    </div>
  );
}
