import React, { useState } from 'react';
import { X, Check, Loader } from 'lucide-react';
import { LLMConfig, LLMProvider, DEFAULT_MODELS } from '../types/llm_config.ts';

interface LLMSettingsPanelProps {
  current: LLMConfig;
  onSave: (config: LLMConfig) => void;
  onClose: () => void;
}

const PROVIDERS: { value: LLMProvider; label: string; needsKey: boolean; needsUrl: boolean }[] = [
  { value: 'gemini',    label: 'Google Gemini',   needsKey: true,  needsUrl: false },
  { value: 'openai',    label: 'OpenAI',           needsKey: true,  needsUrl: false },
  { value: 'anthropic', label: 'Anthropic Claude', needsKey: true,  needsUrl: false },
  { value: 'ollama',    label: 'Ollama (local)',   needsKey: false, needsUrl: true  },
  { value: 'lmstudio',  label: 'LM Studio',        needsKey: false, needsUrl: true  },
];

export default function LLMSettingsPanel({ current, onSave, onClose }: LLMSettingsPanelProps) {
  const [config, setConfig] = useState<LLMConfig>({ ...current });
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'err'>('idle');
  const [errMsg, setErrMsg] = useState('');

  const providerInfo = PROVIDERS.find(p => p.value === config.provider)!;
  const suggestedModels = DEFAULT_MODELS[config.provider];

  const update = (patch: Partial<LLMConfig>) => setConfig(c => ({ ...c, ...patch }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-[#0d0f14] border border-white/10 rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-white uppercase tracking-widest">LLM Settings</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X className="w-4 h-4" /></button>
        </div>

        {/* Provider */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Provider</label>
          <select
            value={config.provider}
            onChange={e => update({ provider: e.target.value as LLMProvider, model: DEFAULT_MODELS[e.target.value as LLMProvider].standard })}
            className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-indigo-500/50"
          >
            {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>

        {/* Model */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Model</label>
          <input
            type="text"
            value={config.model}
            onChange={e => update({ model: e.target.value })}
            className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white font-mono outline-none focus:border-indigo-500/50"
          />
          <div className="flex gap-2">
            {Object.entries(suggestedModels).map(([k, v]) => (
              <button key={k} onClick={() => update({ model: v })}
                className="text-[9px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors">
                {k}: {v}
              </button>
            ))}
          </div>
        </div>

        {/* API Key (hosted providers) */}
        {providerInfo.needsKey && (
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">API Key</label>
            <input
              type="password"
              value={config.apiKey ?? ''}
              onChange={e => update({ apiKey: e.target.value })}
              placeholder="Loaded from env if blank"
              className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white font-mono outline-none focus:border-indigo-500/50 placeholder:text-slate-700"
            />
          </div>
        )}

        {/* Base URL (local providers) */}
        {providerInfo.needsUrl && (
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Base URL</label>
            <input
              type="text"
              value={config.baseUrl ?? ''}
              onChange={e => update({ baseUrl: e.target.value })}
              placeholder="http://localhost:11434"
              className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white font-mono outline-none focus:border-indigo-500/50 placeholder:text-slate-700"
            />
          </div>
        )}

        {/* Temperature */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">
            Temperature — {config.temperature.toFixed(2)}
          </label>
          <input
            type="range" min={0} max={1} step={0.05}
            value={config.temperature}
            onChange={e => update({ temperature: parseFloat(e.target.value) })}
            className="w-full accent-indigo-500"
          />
        </div>

        {/* Status */}
        {status === 'ok' && <div className="text-[10px] text-green-400 font-mono flex items-center gap-1"><Check className="w-3 h-3" /> Connection successful</div>}
        {status === 'err' && <div className="text-[10px] text-red-400 font-mono">{errMsg}</div>}

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={() => { setStatus('testing'); onSave(config); }}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-bold rounded-xl transition-all"
          >
            {status === 'testing' ? <Loader className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            Save & Test
          </button>
          <button onClick={onClose} className="px-4 py-2 bg-white/5 border border-white/10 text-slate-400 text-sm rounded-xl hover:text-white transition-colors">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
