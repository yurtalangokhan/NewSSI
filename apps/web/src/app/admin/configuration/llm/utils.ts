import { JSX } from "react";

import {
  AnthropicIcon,
  AmazonIcon,
  AzureIcon,
  CPUIcon,
  MicrosoftIconSVG,
  MistralIcon,
  MetaIcon,
  GeminiIcon,
  IconProps,
  DeepseekIcon,
  OpenAISVG,
  QwenIcon,
  OllamaIcon,
  ZAIIcon,
} from "@/components/icons/icons";
import { LLMProviderName } from "@/interfaces/llm";
import { SvgAws, SvgOpenrouter, SvgServer } from "@opal/icons";

// Aggregator providers that host models from multiple vendors
export const AGGREGATOR_PROVIDERS = new Set([
  "bedrock",
  "bedrock_converse",
  "openrouter",
  "vertex_ai",
]);

export const getProviderIcon = (
  providerName: string,
  modelName?: string
): (({ size, className }: IconProps) => JSX.Element) => {
  const iconMap: Record<
    string,
    ({ size, className }: IconProps) => JSX.Element
  > = {
    amazon: AmazonIcon,
    aws: SvgAws,
    phi: MicrosoftIconSVG,
    mistral: MistralIcon,
    ministral: MistralIcon,
    mixtral: MistralIcon,
    codestral: MistralIcon,
    pixtral: MistralIcon,
    llama: MetaIcon,
    meta: MetaIcon,
    ollama_chat: OllamaIcon,
    ollama: OllamaIcon,
    gemini: GeminiIcon,
    gemma: GeminiIcon,
    antigravity: GeminiIcon,
    google: GeminiIcon,
    google_genai: GeminiIcon,
    google_vertexai: GeminiIcon,
    vertex_ai: GeminiIcon,
    deepseek: DeepseekIcon,
    claude: AnthropicIcon,
    anthropic: AnthropicIcon,
    openai: OpenAISVG,
    chatgpt: OpenAISVG,
    azure: AzureIcon,
    azure_openai: AzureIcon,
    azure_ai: AzureIcon,
    microsoft: MicrosoftIconSVG,
    qwen: QwenIcon,
    qwq: QwenIcon,
    zai: ZAIIcon,
    vllm: SvgServer,
    bedrock: SvgAws,
    bedrock_converse: SvgAws,
    openrouter: SvgOpenrouter,
    groq: CPUIcon,
    cohere: CPUIcon,
    xai: CPUIcon,
    grok: CPUIcon,
    perplexity: CPUIcon,
    together: CPUIcon,
    fireworks: CPUIcon,
    cerebras: CPUIcon,
    huggingface: CPUIcon,
    nvidia: CPUIcon,
    sambanova: CPUIcon,
  };

  const lowerProviderName = (providerName || "").toLowerCase();
  const lowerModelName = (modelName || "").toLowerCase();

  // 1. Direct provider match for Ollama
  if (lowerProviderName.includes("ollama")) {
    return OllamaIcon;
  }

  // 2. For aggregator providers (bedrock, openrouter, vertex_ai), prioritize showing
  // the vendor icon based on model name (e.g., show Claude icon for Bedrock Claude models)
  if (AGGREGATOR_PROVIDERS.has(lowerProviderName) && lowerModelName) {
    if (
      lowerModelName.includes("claude") ||
      lowerModelName.includes("anthropic")
    )
      return AnthropicIcon;
    if (
      lowerModelName.includes("gpt") ||
      lowerModelName.includes("o1") ||
      lowerModelName.includes("o3") ||
      lowerModelName.includes("dall-e") ||
      lowerModelName.includes("text-embedding")
    )
      return OpenAISVG;
    if (
      lowerModelName.includes("gemini") ||
      lowerModelName.includes("gemma") ||
      lowerModelName.includes("antigravity")
    )
      return GeminiIcon;
    if (lowerModelName.includes("deepseek")) return DeepseekIcon;
    if (
      lowerModelName.includes("mistral") ||
      lowerModelName.includes("ministral") ||
      lowerModelName.includes("mixtral") ||
      lowerModelName.includes("codestral") ||
      lowerModelName.includes("pixtral")
    )
      return MistralIcon;
    if (lowerModelName.includes("llama") || lowerModelName.includes("meta"))
      return MetaIcon;
    if (lowerModelName.includes("qwen") || lowerModelName.includes("qwq"))
      return QwenIcon;
    if (lowerModelName.includes("phi")) return MicrosoftIconSVG;
    if (lowerModelName.includes("nova") || lowerModelName.includes("titan"))
      return AmazonIcon;

    for (const [key, icon] of Object.entries(iconMap)) {
      if (lowerModelName.includes(key)) {
        return icon;
      }
    }
  }

  // 3. Provider-based vendor matching
  if (
    lowerProviderName.includes("gemini") ||
    lowerProviderName.includes("google") ||
    lowerProviderName.includes("vertex") ||
    lowerProviderName.includes("gemma") ||
    lowerProviderName.includes("antigravity")
  )
    return GeminiIcon;
  if (
    lowerProviderName.includes("anthropic") ||
    lowerProviderName.includes("claude")
  )
    return AnthropicIcon;
  if (
    lowerProviderName.includes("openai") ||
    lowerProviderName.includes("azure_openai")
  )
    return OpenAISVG;
  if (lowerProviderName.includes("deepseek")) return DeepseekIcon;
  if (lowerProviderName.includes("mistral")) return MistralIcon;
  if (lowerProviderName.includes("meta") || lowerProviderName.includes("llama"))
    return MetaIcon;
  if (lowerProviderName.includes("qwen") || lowerProviderName.includes("qwq"))
    return QwenIcon;
  if (lowerProviderName.includes("azure")) return AzureIcon;
  if (lowerProviderName.includes("microsoft")) return MicrosoftIconSVG;
  if (
    lowerProviderName.includes("bedrock") ||
    lowerProviderName.includes("amazon") ||
    lowerProviderName.includes("aws")
  )
    return SvgAws;
  if (lowerProviderName.includes("openrouter")) return SvgOpenrouter;
  if (lowerProviderName.includes("zai")) return ZAIIcon;
  if (lowerProviderName.includes("vllm")) return SvgServer;

  // 4. Model-based fallback if provider is generic (custom, etc.)
  if (lowerModelName) {
    if (
      lowerModelName.includes("claude") ||
      lowerModelName.includes("anthropic")
    )
      return AnthropicIcon;
    if (
      lowerModelName.includes("gpt") ||
      lowerModelName.includes("o1") ||
      lowerModelName.includes("o3") ||
      lowerModelName.includes("dall-e") ||
      lowerModelName.includes("text-embedding")
    )
      return OpenAISVG;
    if (
      lowerModelName.includes("gemini") ||
      lowerModelName.includes("gemma") ||
      lowerModelName.includes("antigravity")
    )
      return GeminiIcon;
    if (lowerModelName.includes("deepseek")) return DeepseekIcon;
    if (
      lowerModelName.includes("mistral") ||
      lowerModelName.includes("ministral") ||
      lowerModelName.includes("mixtral") ||
      lowerModelName.includes("codestral") ||
      lowerModelName.includes("pixtral")
    )
      return MistralIcon;
    if (lowerModelName.includes("llama") || lowerModelName.includes("meta"))
      return MetaIcon;
    if (lowerModelName.includes("qwen") || lowerModelName.includes("qwq"))
      return QwenIcon;
    if (lowerModelName.includes("phi")) return MicrosoftIconSVG;
    if (lowerModelName.includes("nova") || lowerModelName.includes("titan"))
      return AmazonIcon;
  }

  // 5. Fallback scan in iconMap
  for (const [key, icon] of Object.entries(iconMap)) {
    if (lowerProviderName.includes(key) || lowerModelName.includes(key)) {
      return icon;
    }
  }

  return CPUIcon;
};

export function canProviderFetchModels(providerName?: string) {
  if (!providerName) return false;
  switch (providerName) {
    case LLMProviderName.BEDROCK:
    case LLMProviderName.OLLAMA_CHAT:
    case LLMProviderName.OPENROUTER:
      return true;
    default:
      return false;
  }
}
