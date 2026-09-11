import { authenticatedFetch } from "@/lib/fetcher";
import { JSX } from "react";
import i18n from "@/i18n/config";
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
import {
  OllamaModelResponse,
  OpenRouterModelResponse,
  BedrockModelResponse,
  ModelConfiguration,
  LLMProviderName,
  BedrockFetchParams,
  OllamaFetchParams,
  OpenRouterFetchParams,
} from "@/interfaces/llm";
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

export const isAnthropic = (provider: string, modelName?: string) =>
  provider === LLMProviderName.ANTHROPIC ||
  !!modelName?.toLowerCase().includes("claude");

/**
 * Fetches Bedrock models directly without any form state dependencies.
 * Uses snake_case params to match API structure.
 */
export const fetchBedrockModels = async (
  params: BedrockFetchParams
): Promise<{ models: ModelConfiguration[]; error?: string }> => {
  if (!params.aws_region_name) {
    return {
      models: [],
      error: i18n.t("llmOnboarding.awsRegionRequiredError"),
    };
  }

  try {
    const response = await authenticatedFetch(
      "/api/admin/llm/bedrock/available-models",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          aws_region_name: params.aws_region_name,
          aws_access_key_id: params.aws_access_key_id,
          aws_secret_access_key: params.aws_secret_access_key,
          aws_bearer_token_bedrock: params.aws_bearer_token_bedrock,
          provider_name: params.provider_name,
        }),
      }
    );

    if (!response.ok) {
      let errorMessage = i18n.t("llmOnboarding.failedFetchModels");
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorMessage;
      } catch {
        // ignore JSON parsing errors
      }
      return { models: [], error: errorMessage };
    }

    const data: BedrockModelResponse[] = await response.json();
    const models: ModelConfiguration[] = data.map((modelData) => ({
      name: modelData.name,
      display_name: modelData.display_name,
      is_visible: false,
      max_input_tokens: modelData.max_input_tokens,
      supports_image_input: modelData.supports_image_input,
      supports_reasoning: false,
    }));

    return { models };
  } catch (error) {
    const errorMessage =
      error instanceof Error
        ? error.message
        : i18n.t("llmOnboarding.unknownError");
    return { models: [], error: errorMessage };
  }
};

/**
 * Fetches Ollama models directly without any form state dependencies.
 * Uses snake_case params to match API structure.
 */
export const fetchOllamaModels = async (
  params: OllamaFetchParams
): Promise<{ models: ModelConfiguration[]; error?: string }> => {
  const apiBase = params.api_base;
  if (!apiBase) {
    return { models: [], error: i18n.t("llmOnboarding.apiBaseRequiredError") };
  }

  try {
    const response = await authenticatedFetch(
      "/api/admin/llm/ollama/available-models",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          api_base: apiBase,
          provider_name: params.provider_name,
        }),
      }
    );

    if (!response.ok) {
      let errorMessage = i18n.t("llmOnboarding.failedFetchModels");
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorMessage;
      } catch {
        // ignore JSON parsing errors
      }
      return { models: [], error: errorMessage };
    }

    const data: OllamaModelResponse[] = await response.json();
    const models: ModelConfiguration[] = data.map((modelData) => ({
      name: modelData.name,
      display_name: modelData.display_name,
      is_visible: true,
      max_input_tokens: modelData.max_input_tokens,
      supports_image_input: modelData.supports_image_input,
      supports_reasoning: false,
    }));

    return { models };
  } catch (error) {
    const errorMessage =
      error instanceof Error
        ? error.message
        : i18n.t("llmOnboarding.unknownError");
    return { models: [], error: errorMessage };
  }
};

/**
 * Fetches OpenRouter models directly without any form state dependencies.
 * Uses snake_case params to match API structure.
 */
export const fetchOpenRouterModels = async (
  params: OpenRouterFetchParams
): Promise<{ models: ModelConfiguration[]; error?: string }> => {
  const apiBase = params.api_base;
  const apiKey = params.api_key;
  if (!apiBase) {
    return { models: [], error: i18n.t("llmOnboarding.apiBaseRequiredError") };
  }
  if (!apiKey) {
    return { models: [], error: i18n.t("llmOnboarding.apiKeyRequiredError") };
  }

  try {
    const response = await authenticatedFetch(
      "/api/admin/llm/openrouter/available-models",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          api_base: apiBase,
          api_key: apiKey,
          provider_name: params.provider_name,
        }),
      }
    );

    if (!response.ok) {
      let errorMessage = i18n.t("llmOnboarding.failedFetchModels");
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorMessage;
      } catch {
        // ignore JSON parsing errors
      }
      return { models: [], error: errorMessage };
    }

    const data: OpenRouterModelResponse[] = await response.json();
    const models: ModelConfiguration[] = data.map((modelData) => ({
      name: modelData.name,
      display_name: modelData.display_name,
      is_visible: true,
      max_input_tokens: modelData.max_input_tokens,
      supports_image_input: modelData.supports_image_input,
      supports_reasoning: false,
    }));

    return { models };
  } catch (error) {
    const errorMessage =
      error instanceof Error
        ? error.message
        : i18n.t("llmOnboarding.unknownError");
    return { models: [], error: errorMessage };
  }
};

/**
 * Fetches models for a provider. Accepts form values directly and maps them
 * to the expected fetch params format internally.
 */
export const fetchModels = async (
  providerName: string,
  formValues: {
    api_base?: string;
    api_key?: string;
    name?: string;
    custom_config?: Record<string, string>;
    model_configurations?: ModelConfiguration[];
  }
) => {
  const customConfig = formValues.custom_config || {};

  switch (providerName) {
    case LLMProviderName.BEDROCK:
      return fetchBedrockModels({
        aws_region_name: customConfig.AWS_REGION_NAME || "",
        aws_access_key_id: customConfig.AWS_ACCESS_KEY_ID,
        aws_secret_access_key: customConfig.AWS_SECRET_ACCESS_KEY,
        aws_bearer_token_bedrock: customConfig.AWS_BEARER_TOKEN_BEDROCK,
        provider_name: formValues.name,
      });
    case LLMProviderName.OLLAMA_CHAT:
      return fetchOllamaModels({
        api_base: formValues.api_base,
        provider_name: formValues.name,
      });
    case LLMProviderName.OPENROUTER:
      return fetchOpenRouterModels({
        api_base: formValues.api_base,
        api_key: formValues.api_key,
        provider_name: formValues.name,
      });
    default:
      return {
        models: [],
        error: i18n.t("llmOnboarding.unknownProvider", { providerName }),
      };
  }
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
