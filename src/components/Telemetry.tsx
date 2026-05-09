import React, { useEffect, useRef } from 'react';
import { Terminal } from 'lucide-react';

export interface LogEntry {
  message: string;
  time: number;
}

interface TelemetryProps {
  logs: LogEntry[];
  isProcessing: boolean;
}

function logColor(message: string): string {
  if (message.startsWith('>>>')) return 'text-indigo-400';
  if (/error|fail|exception/i.test(message)) return 'text-red-400';
  if (message.startsWith('✓') || message.startsWith('✅') || /done|complete|ready/i.test(message)) return 'text-emerald-400';
  if (message.startsWith('---')) return 'text-violet-400';
  return 'text-slate-500';
}

export default function Telemetry({ logs, isProcessing }: TelemetryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  return (
    <div className="bg-white/[0.02] border border-white/5 rounded-xl overflow-hidden flex flex-col" style={{ maxHeight: 180 }}>
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5 flex-shrink-0">
        <Terminal className="w-3 h-3 text-slate-600" />
        <span className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Agent Telemetry</span>
        {isProcessing && (
          <span className="ml-auto flex items-center gap-1 text-[9px] text-indigo-400 font-mono">
            <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
            TRAVERSING_GRAPH_SPACE...
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 font-mono space-y-0.5">
        {logs.length === 0 ? (
          <p className="text-[9px] text-slate-700 px-1">Awaiting session...</p>
        ) : (
          logs.map((log, i) => (
            <div key={i} className="flex gap-2 items-baseline">
              <span className="text-[8px] text-slate-700 flex-shrink-0 tabular-nums">
                {new Date(log.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className={`text-[9px] leading-4 ${logColor(log.message)}`}>{log.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
