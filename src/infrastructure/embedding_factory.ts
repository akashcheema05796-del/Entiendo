import { LLMConfig, getDefaultLLMConfig } from '../types/llm_config.ts';

export interface EmbedderInterface {
  embedQuery(text: string): Promise<number[]>;
}

/**
 * embedding_factory.ts
 * Returns a provider-appropriate text embedder.
 * Falls back to Gemini text-embedding-004 if the active provider has no
 * dedicated embedding model (e.g. Anthropic, LM Studio).
 */
export function getEmbedder(config?: LLMConfig): EmbedderInterface {
  const cfg = config ?? getDefaultLLMConfig();

  switch (cfg.provider) {
    case 'gemini': {
      const { GoogleGenerativeAIEmbeddings } = require('@langchain/google-genai');
      const key = cfg.apiKey ?? process.env.GEMINI_API_KEY;
      if (!key) throw new Error('GEMINI_API_KEY is not set');
      return new GoogleGenerativeAIEmbeddings({ model: 'text-embedding-004', apiKey: key });
    }

    case 'openai': {
      const { OpenAIEmbeddings } = require('@langchain/openai');
      const key = cfg.apiKey ?? process.env.OPENAI_API_KEY;
      if (!key) throw new Error('OPENAI_API_KEY is not set');
      return new OpenAIEmbeddings({ model: 'text-embedding-3-small', apiKey: key });
    }

    case 'ollama': {
      const { OllamaEmbeddings } = require('@langchain/ollama');
      return new OllamaEmbeddings({
        model: 'nomic-embed-text',
        baseUrl: cfg.baseUrl ?? 'http://localhost:11434',
      });
    }

    // Anthropic and LM Studio don't have a dedicated LangChain embedder —
    // fall back to Gemini if available, otherwise no-op embedder.
    default: {
      if (process.env.GEMINI_API_KEY) {
        const { GoogleGenerativeAIEmbeddings } = require('@langchain/google-genai');
        return new GoogleGenerativeAIEmbeddings({ model: 'text-embedding-004', apiKey: process.env.GEMINI_API_KEY });
      }
      if (process.env.OPENAI_API_KEY) {
        const { OpenAIEmbeddings } = require('@langchain/openai');
        return new OpenAIEmbeddings({ model: 'text-embedding-3-small', apiKey: process.env.OPENAI_API_KEY });
      }
      // No embedder available — return null embedder (RAG will be skipped)
      return { embedQuery: async () => [] };
    }
  }
}
