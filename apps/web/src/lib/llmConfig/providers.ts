import type { IconFunctionComponent } from "@opal/types";
import {
  SvgCpu,
  SvgOpenai,
  SvgClaude,
  SvgOllama,
  SvgCloud,
  SvgAws,
  SvgOpenrouter,
  SvgServer,
  SvgAzure,
  SvgGemini,
  SvgLitellm,
} from "@opal/icons";
import { LLMProviderName } from "@/interfaces/llm";

const PROVIDER_ICONS: Record<string, IconFunctionComponent> = {
  [LLMProviderName.OPENAI]: SvgOpenai,
  [LLMProviderName.ANTHROPIC]: SvgClaude,
  [LLMProviderName.VERTEX_AI]: SvgGemini,
  [LLMProviderName.BEDROCK]: SvgAws,
  [LLMProviderName.AZURE]: SvgAzure,
  google_genai: SvgGemini,
  google_vertexai: SvgGemini,
  azure_openai: SvgAzure,
  azure_ai: SvgAzure,
  aws_bedrock: SvgAws,
  openai_compatible: SvgOpenai,
  vllm: SvgServer,
  ollama: SvgOllama,
  litellm: SvgLitellm,
  openrouter: SvgOpenrouter,
  groq: SvgCloud,
  mistral: SvgCloud,
  cohere: SvgCloud,
  deepseek: SvgCloud,
  xai: SvgCloud,
  perplexity: SvgCloud,
  together: SvgCloud,
  fireworks: SvgCloud,
  cerebras: SvgCloud,
  huggingface: SvgCloud,
  nvidia: SvgCloud,
  ibm_watsonx: SvgCloud,
  sambanova: SvgCloud,
  [LLMProviderName.OLLAMA_CHAT]: SvgOllama,

  // fallback
  [LLMProviderName.CUSTOM]: SvgServer,
};

const PROVIDER_PRODUCT_NAMES: Record<string, string> = {
  [LLMProviderName.OPENAI]: "GPT",
  [LLMProviderName.ANTHROPIC]: "Claude",
  [LLMProviderName.VERTEX_AI]: "Gemini",
  [LLMProviderName.BEDROCK]: "Amazon Bedrock",
  [LLMProviderName.AZURE]: "Azure OpenAI",
  litellm: "LiteLLM",
  [LLMProviderName.OLLAMA_CHAT]: "Ollama",
  [LLMProviderName.OPENROUTER]: "OpenRouter",

  // fallback
  [LLMProviderName.CUSTOM]: "Custom Models",
};

const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  [LLMProviderName.OPENAI]: "OpenAI",
  [LLMProviderName.ANTHROPIC]: "Anthropic",
  [LLMProviderName.VERTEX_AI]: "Google Cloud Vertex AI",
  [LLMProviderName.BEDROCK]: "AWS",
  [LLMProviderName.AZURE]: "Microsoft Azure",
  litellm: "LiteLLM",
  [LLMProviderName.OLLAMA_CHAT]: "Ollama",
  [LLMProviderName.OPENROUTER]: "OpenRouter",

  // fallback
  [LLMProviderName.CUSTOM]: "Other providers or self-hosted",
};

export const URL_PROVIDER_TYPES = [
  "ollama",
  "vllm",
  "openai_compatible",
  "litellm",
];

export function getProviderProductName(providerName: string): string {
  return PROVIDER_PRODUCT_NAMES[providerName] ?? providerName;
}

export function getProviderDisplayName(providerName: string): string {
  return PROVIDER_DISPLAY_NAMES[providerName] ?? providerName;
}

export function getProviderIcon(providerName: string): IconFunctionComponent {
  return PROVIDER_ICONS[providerName] ?? SvgCpu;
}
