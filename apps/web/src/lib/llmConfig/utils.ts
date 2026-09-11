export { isEmbeddingModel, isChatModel } from "./modelClassification";
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

/** Whether `hint` names this provider by any handle a caller might hold: its
 * descriptor display name, its provider *type* ("ollama"), or its id/UUID. Flow
 * `LLMModel`/`OllamaModel` nodes store `values.provider` as the type or id,
 * never the display name, so all three have to match. */
const providerMatchesHint = (
  provider: LLMProviderDescriptor,
  hint: string
): boolean => {
  const needle = hint.trim().toLowerCase();
  if (!needle) {
    return false;
  }
  return (
    provider.name?.toLowerCase() === needle ||
    provider.provider?.toLowerCase() === needle ||
    provider.provider_display_name?.toLowerCase() === needle ||
    String(provider.id).toLowerCase() === needle
  );
};

export const findModelConfiguration = (
  llmProviders: LLMProviderDescriptor[],
  modelName: string,
  providerName: string | null = null
): ModelConfiguration | null => {
  // Treat `providerName` as a hint that reorders the search rather than a hard
  // filter: try the providers it names first, then fall back to a full scan so
  // the lookup never fails closed when the hint doesn't line up with any
  // descriptor field (e.g. a flow node storing the provider type or id).
  const orderedProviders = providerName
    ? [
        ...llmProviders.filter((p) => providerMatchesHint(p, providerName)),
        ...llmProviders.filter((p) => !providerMatchesHint(p, providerName)),
      ]
    : llmProviders;

  for (const provider of orderedProviders) {
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

/** Flow-canvas node types that carry a resolvable chat model
 * (apps/agent-service/src/agents/graphs/flow_builder.py `_MODEL_RESOURCE_TYPES`). */
const FLOW_MODEL_NODE_TYPES = new Set(["LLMModel", "OllamaModel"]);

export interface FlowModelRef {
  model: string;
  provider: string | null;
}

type FlowSpecLike =
  | {
      nodes?: Array<{ type?: string; values?: Record<string, unknown> | null }>;
    }
  | null
  | undefined;

/**
 * Collects every chat model a flow-backed agent could actually run, mirroring
 * the backend's resolution in `flow_builder._resolve_model` / `_select_model`:
 *
 * - Each `LLMModel` / `OllamaModel` resource node resolves to its `values.model`,
 *   or the system default model when that field is unset.
 * - An agent node without a wired model resource falls back to the system
 *   default. That only matters when the flow has zero model nodes (every agent
 *   uses the default) or several (an unwired agent may use the default), so the
 *   default is added to the set unless there is exactly one model node.
 *
 * Returns an empty array when the spec is missing or has no nodes — callers
 * treat that as "capability unknown".
 */
export const collectFlowModelRefs = (
  flowSpec: FlowSpecLike,
  defaultModelName: string
): FlowModelRef[] => {
  const nodes = flowSpec?.nodes;
  if (!nodes || nodes.length === 0) {
    return [];
  }

  const modelNodes = nodes.filter(
    (node) => node?.type != null && FLOW_MODEL_NODE_TYPES.has(node.type)
  );

  const refs: FlowModelRef[] = modelNodes.map((node) => {
    const values = node.values ?? {};
    const rawModel =
      typeof values.model === "string" ? values.model.trim() : "";
    const rawProvider =
      typeof values.provider === "string" ? values.provider.trim() : "";
    return {
      model: rawModel || defaultModelName,
      provider: rawProvider || null,
    };
  });

  if (modelNodes.length !== 1) {
    refs.push({ model: defaultModelName, provider: null });
  }

  return refs;
};

/**
 * Whether a flow-backed agent can accept image input: true only when *every*
 * model it could run supports vision. Returns false while the flow spec is
 * still loading or failed to load (empty ref set) — the conservative default.
 */
export const flowModelsSupportImageInput = (
  llmProviders: LLMProviderDescriptor[],
  flowSpec: FlowSpecLike,
  defaultModelName: string
): boolean => {
  const refs = collectFlowModelRefs(flowSpec, defaultModelName);
  if (refs.length === 0) {
    return false;
  }
  return refs.every((ref) =>
    modelSupportsImageInput(llmProviders, ref.model, ref.provider)
  );
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
