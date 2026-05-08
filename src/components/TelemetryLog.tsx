import React, { useEffect, useRef } from 'react';

interface TelemetryLogProps {
  logs: string[];
  isProcessing: boolean;
}

export default function TelemetryLog({ logs, isProcessing }: TelemetryLogProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  return (
    <div className="h-40 bg-[#0a0c10]/80 border border-white/10 rounded-2xl p-4 font-mono flex flex-col shadow-xl flex-shrink-0">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">System_Telemetry</span>
        <div className="flex gap-1">
          {[1, 2, 3].map(i => (
            <div key={i} className="w-1 h-3 bg-indigo-500/40 rounded-full animate-pulse" style={{ animationDelay: `${i * 0.2}s` }} />
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto space-y-1 scrollbar-hide">
        {logs.map((log, i) => (
          <div key={i} className={`text-[10px] flex items-start gap-2 ${
            log.startsWith('>>>') ? 'text-indigo-400' :
            log.includes('[Agent:') ? 'text-violet-400' :
            log.includes('[Agent]') ? 'text-purple-400' :
            log.includes('Error') || log.includes('✗') ? 'text-red-400' :
            log.includes('✓') ? 'text-green-400' :
            log.includes('[Graph]') ? 'text-cyan-400' :
            'text-slate-500'
          }`}>
            <span className="opacity-30 flex-shrink-0">[{new Date().toLocaleTimeString()}]</span>
            <span className="flex-1 leading-tight">{log}</span>
          </div>
        ))}
        <div ref={endRef} />
        {isProcessing && (
          <div className="flex items-center gap-2 text-indigo-400 text-[10px] animate-pulse">
            <span>&gt;</span>
            <span className="font-bold">TRAVERSING_GRAPH_SPACE...</span>
          </div>
        )}
      </div>
    </div>
  );
}
