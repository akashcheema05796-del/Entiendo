import { ChatGoogleGenerativeAI } from '@langchain/google-genai';
import { BaseChatModel } from '@langchain/core/language_models/chat_models';

/**
 * llm_factory.ts
 * Swappable reasoning engines based on task complexity.
 */
export function getLLM(taskType: 'standard' | 'complex' = 'standard', temperature: number = 0.1): BaseChatModel {
  // In our environment, we primarily use Gemini. 
  // We can route via temperature or specific model versions.
  
  const modelName = taskType === 'complex' ? 'gemini-2.5-pro' : 'gemini-2.5-flash';

  if (!process.env.GEMINI_API_KEY) {
    throw new Error('GEMINI_API_KEY is not defined');
  }

  return new ChatGoogleGenerativeAI({
    model: modelName,
    apiKey: process.env.GEMINI_API_KEY,
    temperature: temperature,
  });
}
