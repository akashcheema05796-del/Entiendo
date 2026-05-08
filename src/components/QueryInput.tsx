import React, { useState } from 'react';
import { Send, MessageSquare } from 'lucide-react';
import { CodingTask } from '../types/selection_context.ts';

interface QueryInputProps {
  onSubmit: (query: string, task: CodingTask) => void;
  disabled: boolean;
  selectedCount: number;
}

const TASKS: { value: CodingTask; label: string }[] = [
  { value: 'explain',        label: 'Explain' },
  { value: 'refactor',       label: 'Refactor' },
  { value: 'fix_bug',        label: 'Fix Bug' },
  { value: 'add_feature',    label: 'Add Feature' },
  { value: 'generate_tests', label: 'Tests' },
];

export default function QueryInput({ onSubmit, disabled, selectedCount }: QueryInputProps) {
  const [query, setQuery] = useState('');
  const [task, setTask] = useState<CodingTask>('explain');

  const handleSend = () => {
    if (!query.trim() || disabled) return;
    onSubmit(query.trim(), task);
    setQuery('');
  };

  return (
    <div className="flex flex-col gap-2">
      {/* Task selector */}
      <div className="flex items-center gap-1.5 px-1">
        {TASKS.map(t => (
          <button
            key={t.value}
            onClick={() => setTask(t.value)}
            className={`text-[9px] font-bold px-2.5 py-1 rounded-full transition-all border ${
              task === t.value
                ? 'bg-indigo-600/80 border-indigo-500 text-white'
                : 'bg-white/5 border-white/10 text-slate-500 hover:text-slate-300'
            }`}
          >
            {t.label}
          </button>
        ))}
        {selectedCount > 0 && (
          <span className="ml-auto text-[9px] font-mono text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 rounded-full">
            {selectedCount} node{selectedCount !== 1 ? 's' : ''} selected
          </span>
        )}
      </div>

      {/* Input bar */}
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
            placeholder={selectedCount > 0 ? `${task} selected nodes...` : 'Select nodes in the graph, then ask anything...'}
            className="flex-1 bg-transparent py-3 text-sm font-medium text-white outline-none placeholder:text-slate-600"
          />
          <button
            onClick={handleSend}
            disabled={disabled || !query.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 text-white p-3 rounded-2xl transition-all shadow-lg active:scale-95 group"
          >
            <Send className="w-5 h-5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </button>
        </div>
      </div>
    </div>
  );
}
