import React, { useState } from 'react';
import { FileCode, X, Copy, Check } from 'lucide-react';

interface FileViewerProps {
  path: string;
  content: string;
  onClose: () => void;
}

const KEYWORDS_JS = /\b(import|export|from|const|let|var|function|class|interface|type|return|async|await|if|else|for|while|try|catch|finally|new|extends|implements|default|void|null|undefined|true|false|typeof|instanceof|of|in|switch|case|break|continue|throw|static|readonly|abstract|private|public|protected|override|declare|enum|namespace|module|require|yield|delete)\b/g;
const KEYWORDS_PY = /\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|pass|break|continue|raise|yield|lambda|and|or|not|in|is|True|False|None|global|nonlocal|assert|del|async|await)\b/g;
const STRINGS = /(['"`])((?:\\.|(?!\1)[^\\])*?)\1/g;
const COMMENTS_JS = /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm;
const COMMENTS_PY = /(#.*$)/gm;
const NUMBERS = /\b(\d+\.?\d*)\b/g;
const TYPES = /\b(string|number|boolean|object|any|unknown|never|Promise|Array|Record|Partial|Required|Readonly|Map|Set|void|null)\b/g;

function escape(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function highlight(code: string, ext: string): string {
  const safe = escape(code);
  if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) {
    return safe
      .replace(COMMENTS_JS, '<span class="tok-comment">$1</span>')
      .replace(STRINGS, '<span class="tok-string">$1$2$1</span>')
      .replace(TYPES, '<span class="tok-type">$1</span>')
      .replace(KEYWORDS_JS, '<span class="tok-keyword">$1</span>')
      .replace(NUMBERS, '<span class="tok-number">$1</span>');
  }
  if (ext === '.py') {
    return safe
      .replace(COMMENTS_PY, '<span class="tok-comment">$1</span>')
      .replace(STRINGS, '<span class="tok-string">$1$2$1</span>')
      .replace(KEYWORDS_PY, '<span class="tok-keyword">$1</span>')
      .replace(NUMBERS, '<span class="tok-number">$1</span>');
  }
  return safe;
}

export default function FileViewer({ path, content, onClose }: FileViewerProps) {
  const [copied, setCopied] = useState(false);
  const ext = '.' + path.split('.').pop();
  const lines = content.split('\n');
  const highlighted = highlight(content, ext);
  const highlightedLines = highlighted.split('\n');

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-white/5 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileCode className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
          <span className="text-[10px] font-mono font-bold text-slate-400 truncate">{path}</span>
          <span className="text-[9px] text-slate-600 flex-shrink-0">{lines.length} lines</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-500 hover:text-slate-300 text-[9px] transition-all"
          >
            {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 text-slate-500 hover:text-slate-300 transition-all">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Code body */}
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <tbody>
            {highlightedLines.map((line, i) => (
              <tr key={i} className="hover:bg-white/[0.02] group">
                <td className="select-none text-right pr-4 pl-3 py-0 text-[10px] font-mono text-slate-700 group-hover:text-slate-500 w-10 align-top leading-5 sticky left-0 bg-[#0a0c10] border-r border-white/5">
                  {i + 1}
                </td>
                <td className="pl-4 pr-4 py-0 leading-5">
                  <pre
                    className="text-[10px] font-mono text-slate-300 whitespace-pre"
                    dangerouslySetInnerHTML={{ __html: line || ' ' }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <style>{`
        .tok-keyword  { color: #a78bfa; }
        .tok-string   { color: #86efac; }
        .tok-comment  { color: #475569; font-style: italic; }
        .tok-number   { color: #fbbf24; }
        .tok-type     { color: #67e8f9; }
      `}</style>
    </div>
  );
}
