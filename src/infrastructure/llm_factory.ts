import { BaseChatModel } from '@langchain/core/language_models/chat_models';
import { LLMConfig, getDefaultLLMConfig } from '../types/llm_config.ts';

/**
 * llm_factory.ts
 * Single entry point for all LLM instantiation.
 * Routes to the correct LangChain provider based on LLMConfig.
 * No provider SDK is imported outside this file.
 */
export function getLLM(config?: LLMConfig): BaseChatModel {
  const cfg = config ?? getDefaultLLMConfig();

  switch (cfg.provider) {
    case 'gemini': {
      const { ChatGoogleGenerativeAI } = require('@langchain/google-genai');
      const key = cfg.apiKey ?? process.env.GEMINI_API_KEY;
      if (!key) throw new Error('GEMINI_API_KEY is not set');
      return new ChatGoogleGenerativeAI({ model: cfg.model, apiKey: key, temperature: cfg.temperature });
    }

    case 'openai': {
      const { ChatOpenAI } = require('@langchain/openai');
      const key = cfg.apiKey ?? process.env.OPENAI_API_KEY;
      if (!key) throw new Error('OPENAI_API_KEY is not set');
      return new ChatOpenAI({ model: cfg.model, apiKey: key, temperature: cfg.temperature });
    }

    case 'anthropic': {
      const { ChatAnthropic } = require('@langchain/anthropic');
      const key = cfg.apiKey ?? process.env.ANTHROPIC_API_KEY;
      if (!key) throw new Error('ANTHROPIC_API_KEY is not set');
      return new ChatAnthropic({ model: cfg.model, apiKey: key, temperature: cfg.temperature });
    }

    case 'ollama': {
      const { ChatOllama } = require('@langchain/ollama');
      return new ChatOllama({
        model: cfg.model,
        baseUrl: cfg.baseUrl ?? 'http://localhost:11434',
        temperature: cfg.temperature,
      });
    }

    case 'lmstudio': {
      // LM Studio exposes an OpenAI-compatible API
      const { ChatOpenAI } = require('@langchain/openai');
      return new ChatOpenAI({
        model: cfg.model,
        apiKey: 'lmstudio',
        configuration: { baseURL: cfg.baseUrl ?? 'http://localhost:1234/v1' },
        temperature: cfg.temperature,
      });
    }

    default:
      throw new Error(`Unknown LLM provider: ${(cfg as any).provider}`);
  }
}

/** Convenience: get the "standard" (fast) model for the active config */
export function getStandardLLM(config?: LLMConfig): BaseChatModel {
  return getLLM(config);
}

/** Convenience: get the "complex" (capable) model — uses Pro/large variant */
export function getComplexLLM(config?: LLMConfig): BaseChatModel {
  const cfg = config ?? getDefaultLLMConfig();
  const { DEFAULT_MODELS } = require('../types/llm_config.ts');
  return getLLM({ ...cfg, model: DEFAULT_MODELS[cfg.provider]?.complex ?? cfg.model });
}
