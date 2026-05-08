import React from 'react';
import { MessageSquare, Wrench, Bug, Zap, TestTube } from 'lucide-react';
import { CodingTask } from '../types/selection_context.ts';

interface ActionBarProps {
  selectedCount: number;
  onAction: (task: CodingTask) => void;
  disabled: boolean;
}

const ACTIONS: { task: CodingTask; label: string; icon: React.ReactNode; color: string }[] = [
  { task: 'explain',        label: 'Explain',     icon: <MessageSquare className="w-3 h-3" />, color: 'indigo' },
  { task: 'refactor',       label: 'Refactor',    icon: <Wrench className="w-3 h-3" />,        color: 'violet' },
  { task: 'fix_bug',        label: 'Fix Bug',     icon: <Bug className="w-3 h-3" />,           color: 'red' },
  { task: 'add_feature',    label: 'Add Feature', icon: <Zap className="w-3 h-3" />,           color: 'amber' },
  { task: 'generate_tests', label: 'Tests',       icon: <TestTube className="w-3 h-3" />,      color: 'green' },
];

const COLOR_CLASSES: Record<string, string> = {
  indigo: 'bg-indigo-500/10 hover:bg-indigo-500/20 border-indigo-500/30 text-indigo-400',
  violet: 'bg-violet-500/10 hover:bg-violet-500/20 border-violet-500/30 text-violet-400',
  red:    'bg-red-500/10 hover:bg-red-500/20 border-red-500/30 text-red-400',
  amber:  'bg-amber-500/10 hover:bg-amber-500/20 border-amber-500/30 text-amber-400',
  green:  'bg-green-500/10 hover:bg-green-500/20 border-green-500/30 text-green-400',
};

export default function ActionBar({ selectedCount, onAction, disabled }: ActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold">
        Quick Actions — {selectedCount} node{selectedCount !== 1 ? 's' : ''}
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {ACTIONS.map(({ task, label, icon, color }) => (
          <button
            key={task}
            onClick={() => onAction(task)}
            disabled={disabled}
            className={`flex items-center gap-1.5 px-2 py-1.5 rounded-xl border text-[10px] font-bold transition-all disabled:opacity-30 ${COLOR_CLASSES[color]}`}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
