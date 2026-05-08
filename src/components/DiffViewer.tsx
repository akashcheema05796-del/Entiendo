import React, { useState } from 'react';
import { Check, X, FileCode, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'motion/react';

interface FileDiff {
  filePath: string | null;
  original: string;
  modified: string;
  appliedBlocks: number;
}

interface DiffViewerProps {
  // Multi-file: array of diffs
  diffs?: FileDiff[];
  // Legacy single-file props (kept for backwards-compat)
  filePath?: string | null;
  original?: string;
  modified?: string;
  appliedBlocks?: number;
  onAccept: () => void;
  onReject: () => void;
}

export default function DiffViewer({ diffs, filePath, original, modified, appliedBlocks, onAccept, onReject }: DiffViewerProps) {
  const [activeIndex, setActiveIndex] = useState(0);

  // Normalise to array
  const allDiffs: FileDiff[] = diffs ?? [{ filePath: filePath ?? null, original: original ?? '', modified: modified ?? '', appliedBlocks: appliedBlocks ?? 0 }];
  const current = allDiffs[activeIndex] ?? allDiffs[0];
  const fileName = current.filePath ? current.filePath.split('/').pop() : 'unknown file';
  const totalBlocks = allDiffs.reduce((sum, d) => sum + d.appliedBlocks, 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-3"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <FileCode className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-mono truncate max-w-[160px]">{fileName}</span>
          <span className="px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 rounded text-[9px] font-bold">
            {current.appliedBlocks} change{current.appliedBlocks !== 1 ? 's' : ''}
          </span>
          {allDiffs.length > 1 && (
            <span className="px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded text-[9px] font-bold">
              {allDiffs.length} files · {totalBlocks} total
            </span>
          )}
        </div>

        {/* File navigator */}
        {allDiffs.length > 1 && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveIndex(i => Math.max(0, i - 1))}
              disabled={activeIndex === 0}
              className="p-1 rounded text-slate-500 hover:text-slate-300 disabled:opacity-30"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="text-[9px] font-mono text-slate-500">{activeIndex + 1}/{allDiffs.length}</span>
            <button
              onClick={() => setActiveIndex(i => Math.min(allDiffs.length - 1, i + 1))}
              disabled={activeIndex === allDiffs.length - 1}
              className="p-1 rounded text-slate-500 hover:text-slate-300 disabled:opacity-30"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* File tabs for multi-file */}
      {allDiffs.length > 1 && (
        <div className="flex gap-1 overflow-x-auto scrollbar-hide">
          {allDiffs.map((d, i) => (
            <button
              key={i}
              onClick={() => setActiveIndex(i)}
              className={`flex-shrink-0 px-2 py-1 rounded-lg text-[9px] font-mono transition-all ${
                i === activeIndex
                  ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
                  : 'bg-white/5 text-slate-500 border border-white/5 hover:text-slate-300'
              }`}
            >
              {d.filePath?.split('/').pop() ?? 'file'}
            </button>
          ))}
        </div>
      )}

      {/* Diff panes */}
      <div className="grid grid-cols-2 gap-2 max-h-64 overflow-hidden">
        <div className="bg-red-950/30 border border-red-500/20 rounded-xl p-3 overflow-y-auto">
          <div className="text-[9px] text-red-400 font-mono font-bold mb-2 uppercase tracking-widest sticky top-0 bg-red-950/80">
            — Before
          </div>
          <pre className="text-[10px] font-mono text-red-200/80 whitespace-pre-wrap break-all">
            {current.original || '(empty)'}
          </pre>
        </div>
        <div className="bg-green-950/30 border border-green-500/20 rounded-xl p-3 overflow-y-auto">
          <div className="text-[9px] text-green-400 font-mono font-bold mb-2 uppercase tracking-widest sticky top-0 bg-green-950/80">
            + After
          </div>
          <pre className="text-[10px] font-mono text-green-200/80 whitespace-pre-wrap break-all">
            {current.modified || '(empty)'}
          </pre>
        </div>
      </div>

      {/* Actions */}
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
          <Check className="w-3 h-3" /> Apply {allDiffs.length > 1 ? 'All Files' : 'Changes'}
        </button>
      </div>
    </motion.div>
  );
}
