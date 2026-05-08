export type LLMProvider = 'gemini' | 'openai' | 'anthropic' | 'ollama' | 'lmstudio';

export interface LLMConfig {
  provider: LLMProvider;
  model: string;
  temperature: number;
  baseUrl?: string;   // for ollama / lmstudio
  apiKey?: string;    // for hosted providers (never logged)
}

export const DEFAULT_MODELS: Record<LLMProvider, { standard: string; complex: string }> = {
  gemini:    { standard: 'gemini-2.5-flash', complex: 'gemini-2.5-pro' },
  openai:    { standard: 'gpt-4o-mini',      complex: 'gpt-4o' },
  anthropic: { standard: 'claude-haiku-4-5-20251001', complex: 'claude-sonnet-4-6' },
  ollama:    { standard: 'llama3.2',         complex: 'llama3.2' },
  lmstudio:  { standard: 'local-model',      complex: 'local-model' },
};

export function getDefaultLLMConfig(): LLMConfig {
  if (process.env.GEMINI_API_KEY) {
    return { provider: 'gemini', model: 'gemini-2.5-flash', temperature: 0.1 };
  }
  if (process.env.OPENAI_API_KEY) {
    return { provider: 'openai', model: 'gpt-4o-mini', temperature: 0.1 };
  }
  if (process.env.ANTHROPIC_API_KEY) {
    return { provider: 'anthropic', model: 'claude-haiku-4-5-20251001', temperature: 0.1 };
  }
  return { provider: 'ollama', model: 'llama3.2', temperature: 0.1, baseUrl: 'http://localhost:11434' };
}
