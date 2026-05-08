import React, { useState } from 'react';
import { Check, X, FileCode, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'motion/react';

export interface FileDiff {
  original: string;
  modified: string;
  appliedBlocks: number;
  filePath: string | null;
}

interface DiffViewerProps {
  files: FileDiff[];
  onAccept: () => void;
  onReject: () => void;
}

export default function DiffViewer({ files, onAccept, onReject }: DiffViewerProps) {
  const [index, setIndex] = useState(0);
  const current = files[index];
  const fileName = current.filePath ? current.filePath.split('/').pop() : 'unknown file';
  const isMulti = files.length > 1;

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
          <span className="font-mono">{fileName}</span>
          <span className="px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 rounded text-[9px] font-bold">
            {current.appliedBlocks} change{current.appliedBlocks !== 1 ? 's' : ''}
          </span>
        </div>

        {/* File navigation — only shown for multi-file diffs */}
        {isMulti && (
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] font-mono text-slate-500">
              {index + 1} / {files.length}
            </span>
            <button
              onClick={() => setIndex(i => Math.max(0, i - 1))}
              disabled={index === 0}
              className="p-0.5 rounded text-slate-500 hover:text-slate-300 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setIndex(i => Math.min(files.length - 1, i + 1))}
              disabled={index === files.length - 1}
              className="p-0.5 rounded text-slate-500 hover:text-slate-300 disabled:opacity-30 transition-colors"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Diff panels */}
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
      <div className="flex items-center justify-between pt-1">
        {isMulti && (
          <span className="text-[9px] font-mono text-slate-600">
            {files.reduce((n, f) => n + f.appliedBlocks, 0)} total changes across {files.length} files
          </span>
        )}
        <div className="flex gap-2 ml-auto">
          <button
            onClick={onReject}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 text-[11px] font-bold rounded-xl transition-all"
          >
            <X className="w-3 h-3" /> Reject All
          </button>
          <button
            onClick={onAccept}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 text-[11px] font-bold rounded-xl transition-all"
          >
            <Check className="w-3 h-3" /> Apply All
          </button>
        </div>
      </div>
    </motion.div>
  );
}
