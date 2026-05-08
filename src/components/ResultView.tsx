import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import mermaid from 'mermaid';
import DiffViewer from './DiffViewer.tsx';
import { FileDiff } from './DiffViewer.tsx';

interface ResultViewProps {
  outputType: string;
  content: string;
  pendingDiffId?: string | null;
  onAcceptDiff?: () => void;
  onRejectDiff?: () => void;
}

function MermaidView({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !chart) return;
    mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
    mermaid.render(`mermaid-${Math.random().toString(36).slice(2, 9)}`, chart)
      .then(({ svg }) => { if (ref.current) ref.current.innerHTML = svg; })
      .catch(err => { if (ref.current) ref.current.textContent = `Diagram error: ${err.message}`; });
  }, [chart]);
  return <div ref={ref} className="w-full flex justify-center py-4 bg-white/5 rounded-xl overflow-hidden" />;
}

export default function ResultView({ outputType, content, pendingDiffId, onAcceptDiff, onRejectDiff }: ResultViewProps) {
  if (outputType === 'diff_proposal') {
    try {
      const parsed = JSON.parse(content) as { files: FileDiff[] };
      return (
        <DiffViewer
          files={parsed.files}
          onAccept={onAcceptDiff ?? (() => {})}
          onReject={onRejectDiff ?? (() => {})}
        />
      );
    } catch {
      return <pre className="text-red-400 text-[10px] font-mono">{content}</pre>;
    }
  }

  if (outputType === 'mermaid') {
    return <MermaidView chart={content} />;
  }

  return (
    <div className="prose prose-invert prose-xs max-w-none text-xs leading-relaxed text-slate-300">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
