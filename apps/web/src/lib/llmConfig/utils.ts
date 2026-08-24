import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import {
  DefaultModel,
  LLMProviderDescriptor,
  ModelConfiguration,
} from "@/interfaces/llm";
import { LlmDescriptor } from "@/lib/hooks";

export function getFinalLLM(
  llmProviders: LLMProviderDescriptor[],
  persona: MinimalPersonaSnapshot | null,
  currentLlm: LlmDescriptor | null,
  defaultText?: DefaultModel | null
): [string, string] {
  const defaultProvider = defaultText
    ? llmProviders.find((p) => p.id === defaultText.provider_id)
    : llmProviders.find((p) =>
        p.model_configurations.some((m) => m.is_visible)
      );

  let provider = defaultProvider?.provider || "";
  let model =
    defaultText?.model_name ||
    defaultProvider?.model_configurations.find((m) => m.is_visible)?.name ||
    "";

  if (persona) {
    // Map "provider override" to actual LLLMProvider
    if (persona.llm_model_provider_override) {
      const underlyingProvider = llmProviders.find(
        (item: LLMProviderDescriptor) =>
          item.name === persona.llm_model_provider_override
      );
      provider = underlyingProvider?.provider || provider;
    }
    model = persona.llm_model_version_override || model;
  }

  if (currentLlm) {
    provider = currentLlm.provider || provider;
    model = currentLlm.modelName || model;
  }

  return [provider, model];
}

export function getLLMProviderOverrideForPersona(
  liveAgent: MinimalPersonaSnapshot,
  llmProviders: LLMProviderDescriptor[]
): LlmDescriptor | null {
  const overrideProvider = liveAgent.llm_model_provider_override;
  const overrideModel = liveAgent.llm_model_version_override;

  if (!overrideModel) {
    return null;
  }

  const matchingProvider = llmProviders.find(
    (provider) =>
      (overrideProvider ? provider.name === overrideProvider : true) &&
      provider.model_configurations
        .map((modelConfiguration) => modelConfiguration.name)
        .includes(overrideModel)
  );

  if (matchingProvider) {
    return {
      name: matchingProvider.name,
      provider: matchingProvider.provider,
      modelName: overrideModel,
    };
  }

  return null;
}

export const structureValue = (
  name: string,
  provider: string,
  modelName: string
) => {
  return `${name}__${provider}__${modelName}`;
};

export const parseLlmDescriptor = (value: string): LlmDescriptor => {
  const [displayName, provider, modelName] = value.split("__");
  if (displayName === undefined) {
    return { name: "Unknown", provider: "", modelName: "" };
  }

  return {
    name: displayName,
    provider: provider ?? "",
    modelName: modelName ?? "",
  };
};

export interface DefaultModelProviderGroup {
  providerKey: string | number;
  providerType: string;
  models: string[];
}

export interface ResolvedDefaultModelSelection {
  providerKey: string | number | undefined;
  modelName: string | undefined;
}

/**
 * Resolves a user's saved default-model preference into a provider key +
 * model name, understanding every format it may have been written in:
 *
 * - Modern: separate `default_model` / `default_provider_id` fields.
 * - Legacy composite: "providerId:modelName".
 * - Chat Preferences composite (via `structureValue`):
 *   "providerDisplayName__providerType__modelName".
 * - Bare model name with no provider info, resolved by scanning groups.
 */
export function resolveDefaultModelSelection(
  defaultModel: string | null | undefined,
  defaultProviderId: string | null | undefined,
  providerGroups: DefaultModelProviderGroup[]
): ResolvedDefaultModelSelection {
  if (!defaultModel) {
    return { providerKey: undefined, modelName: undefined };
  }

  let providerKey: string | number | undefined = defaultProviderId ?? undefined;
  let modelName: string | undefined = defaultModel;

  if (!providerKey) {
    const firstColonIndex = defaultModel.indexOf(":");
    if (firstColonIndex > 0) {
      const possibleProviderKey = defaultModel.slice(0, firstColonIndex);
      const hasMatchingProviderKey = providerGroups.some(
        (group) => String(group.providerKey) === possibleProviderKey
      );
      if (hasMatchingProviderKey) {
        providerKey = possibleProviderKey;
        modelName = defaultModel.slice(firstColonIndex + 1);
      }
    }
  }

  if (!providerKey) {
    const { provider: providerType, modelName: parsedModelName } =
      parseLlmDescriptor(defaultModel);
    if (providerType && parsedModelName) {
      const matchingProvider = providerGroups.find(
        (group) =>
          group.providerType === providerType &&
          group.models.includes(parsedModelName)
      );
      if (matchingProvider) {
        providerKey = matchingProvider.providerKey;
        modelName = parsedModelName;
      }
    }
  }

  if (!providerKey) {
    const matchingProvider = providerGroups.find((group) =>
      group.models.includes(modelName as string)
    );
    if (matchingProvider) {
      providerKey = matchingProvider.providerKey;
    }
  }

  return { providerKey, modelName };
}

export const findModelInModelConfigurations = (
  modelConfigurations: ModelConfiguration[],
  modelName: string
): ModelConfiguration | null => {
  return modelConfigurations.find((m) => m.name === modelName) || null;
};

export const findModelConfiguration = (
  llmProviders: LLMProviderDescriptor[],
  modelName: string,
  providerName: string | null = null
): ModelConfiguration | null => {
  if (providerName) {
    const provider = llmProviders.find((p) => p.name === providerName);
    return provider
      ? findModelInModelConfigurations(provider.model_configurations, modelName)
      : null;
  }

  for (const provider of llmProviders) {
    const modelConfiguration = findModelInModelConfigurations(
      provider.model_configurations,
      modelName
    );
    if (modelConfiguration) {
      return modelConfiguration;
    }
  }

  return null;
};

export const modelSupportsImageInput = (
  llmProviders: LLMProviderDescriptor[],
  modelName: string,
  providerName: string | null = null
): boolean => {
  const modelConfiguration = findModelConfiguration(
    llmProviders,
    modelName,
    providerName
  );
  return modelConfiguration?.supports_image_input || false;
};

export function getDisplayName(
  agent: MinimalPersonaSnapshot,
  llmProviders: LLMProviderDescriptor[]
): string | undefined {
  const llmDescriptor = getLLMProviderOverrideForPersona(
    agent,
    llmProviders ?? []
  );
  const llmProvider = llmProviders?.find(
    (llmProvider) => llmProvider.name === agent.llm_model_provider_override
  );
  const modelConfig = llmProvider?.model_configurations.find(
    (modelConfig) => modelConfig.name === llmDescriptor?.modelName
  );
  return modelConfig?.display_name;
}
