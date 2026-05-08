import React from 'react';
import { Check, X, FileCode } from 'lucide-react';
import { motion } from 'motion/react';

interface DiffViewerProps {
  filePath: string | null;
  original: string;
  modified: string;
  appliedBlocks: number;
  onAccept: () => void;
  onReject: () => void;
}

export default function DiffViewer({ filePath, original, modified, appliedBlocks, onAccept, onReject }: DiffViewerProps) {
  const fileName = filePath ? filePath.split('/').pop() : 'unknown file';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-3"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <FileCode className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-mono">{fileName}</span>
          <span className="px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 rounded text-[9px] font-bold">
            {appliedBlocks} change{appliedBlocks !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 max-h-64 overflow-hidden">
        <div className="bg-red-950/30 border border-red-500/20 rounded-xl p-3 overflow-y-auto">
          <div className="text-[9px] text-red-400 font-mono font-bold mb-2 uppercase tracking-widest sticky top-0 bg-red-950/80">
            — Before
          </div>
          <pre className="text-[10px] font-mono text-red-200/80 whitespace-pre-wrap break-all">
            {original || '(empty)'}
          </pre>
        </div>
        <div className="bg-green-950/30 border border-green-500/20 rounded-xl p-3 overflow-y-auto">
          <div className="text-[9px] text-green-400 font-mono font-bold mb-2 uppercase tracking-widest sticky top-0 bg-green-950/80">
            + After
          </div>
          <pre className="text-[10px] font-mono text-green-200/80 whitespace-pre-wrap break-all">
            {modified || '(empty)'}
          </pre>
        </div>
      </div>

      <div className="flex gap-2 justify-end pt-1">
        <button
          onClick={onReject}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 text-[11px] font-bold rounded-xl transition-all"
        >
          <X className="w-3 h-3" /> Reject
        </button>
        <button
          onClick={onAccept}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 text-[11px] font-bold rounded-xl transition-all"
        >
          <Check className="w-3 h-3" /> Apply Changes
        </button>
      </div>
    </motion.div>
  );
}
