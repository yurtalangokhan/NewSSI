import { LLMProviderName } from "@/interfaces/llm";
export const isAnthropic = (provider: string, modelName?: string) =>
  provider === LLMProviderName.ANTHROPIC ||
  !!modelName?.toLowerCase().includes("claude");
