"use client";
import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";

import { useEffect } from "react";
import { useMemo } from "react";
import { useRef } from "react";
import { useState } from "react";
import { parseLlmDescriptor } from "@/lib/llmConfig/utils";
import { ChatSession } from "@/lib/api/domains/chat/types";
import { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import { DefaultModel } from "@/interfaces/llm";
import { LLMProviderDescriptor } from "@/interfaces/llm";
import { isAnthropic } from "@/lib/api/domains/model-providers/model-classification";
import { useUser } from "@/providers/UserProvider";
import { SEARCH_TOOL_ID } from "@/lib/api/domains/tools/constants";
import { updateTemperatureOverrideForChatSession } from "@/lib/api/domains/chat/api";

import useSWR from "swr";
import { fetchAvailableModels } from "@/lib/api/domains/model-providers/api";

import { useSWRConfig } from "swr";
import { fetchLLMProviders } from "@/lib/api/domains/model-providers/api";
import { fetchLLMPersonaProviders } from "@/lib/api/domains/model-providers/api";
import { fetchAdminLLMProvider } from "@/lib/api/domains/model-providers/api";
import { fetchAdminLLMBuiltInOptions } from "@/lib/api/domains/model-providers/api";
import { LLMProviderResponse } from "@/interfaces/llm";
import { LLMProviderView } from "@/interfaces/llm";
import { WellKnownLLMProviderDescriptor } from "@/interfaces/llm";

import { useCallback } from "react";
import { fetchProviders } from "@/lib/api/domains/model-providers/api";
import { fetchWellKnownProviders } from "@/lib/api/domains/model-providers/api";
import { fetchOllamaStatus } from "@/lib/api/domains/model-providers/api";
import { fetchOllamaModels } from "@/lib/api/domains/model-providers/api";
import { deleteOllamaModel } from "@/lib/api/domains/model-providers/api";
import { reorderProviders } from "@/lib/api/domains/model-providers/api";
import { updateProviderDefaultModel } from "@/lib/api/domains/model-providers/api";
import type { AllProvidersResponse } from "@/interfaces/llm";
import type { BuiltinOllamaStatus } from "@/interfaces/llm";
import type { OllamaModelResponse } from "@/interfaces/llm";
import type { WellKnownLangChainProvider } from "@/interfaces/llm";

const EMPTY_LLM_PROVIDERS: LLMProviderDescriptor[] = [];

export interface LlmDescriptor {
  name: string;
  provider: string;
  modelName: string;
  providerId?: string;
}

export interface LlmManager {
  currentLlm: LlmDescriptor;
  updateCurrentLlm: (newOverride: LlmDescriptor) => void;
  temperature: number;
  updateTemperature: (temperature: number) => void;
  updateModelOverrideBasedOnChatSession: (chatSession?: ChatSession) => void;
  imageFilesPresent: boolean;
  updateImageFilesPresent: (present: boolean) => void;
  liveAgent: MinimalPersonaSnapshot | null;
  maxTemperature: number;
  llmProviders: LLMProviderDescriptor[] | undefined;
  isLoadingProviders: boolean;
  hasAnyProvider: boolean;
}

export function getDefaultLlmDescriptor(
  llmProviders: LLMProviderDescriptor[],
  defaultText?: DefaultModel | null
): LlmDescriptor | null {
  if (defaultText) {
    const provider = llmProviders.find(
      (p) => String(p.id) === String(defaultText.provider_id)
    );
    if (provider) {
      return {
        name: provider.name,
        provider: provider.provider,
        modelName: defaultText.model_name,
        providerId: String(provider.id),
      };
    }
  }
  // Fallback: first provider with visible models
  const firstLlmProvider = llmProviders.find(
    (provider) => provider.model_configurations.length > 0
  );
  if (firstLlmProvider) {
    const firstModel = firstLlmProvider.model_configurations.find(
      (m) => m.is_visible
    );
    return {
      name: firstLlmProvider.name,
      provider: firstLlmProvider.provider,
      modelName: firstModel?.name ?? "",
      providerId: String(firstLlmProvider.id),
    };
  }
  return null;
}

export function getValidLlmDescriptorForProviders(
  modelName: string | null | undefined,
  llmProviders: LLMProviderDescriptor[] | undefined | null
): LlmDescriptor {
  // Return early if providers haven't loaded yet (undefined/null)
  // Empty arrays are valid (user has no provider access for this assistant)
  if (llmProviders === undefined || llmProviders === null) {
    return { name: "", provider: "", modelName: "" };
  }

  if (modelName) {
    // COMPOSITE FORMAT (backward compat): stored as "providerId:modelName" before separate default_provider_id field existed.
    // Exclude strings with "__" because those use the older parseLlmDescriptor format ("providerName__modelName").
    if (modelName.includes(":") && !modelName.includes("__")) {
      const parts = modelName.split(":");
      const providerId = parts[0];
      const extractedModelName = parts.slice(1).join(":");

      const provider = llmProviders.find(
        (p) => String(p.id) === providerId || p.id === providerId
      );
      if (provider) {
        const model = provider.model_configurations.find(
          (m) => m.name === extractedModelName
        );
        if (model) {
          return {
            modelName: extractedModelName,
            name: provider.name,
            provider: provider.provider,
            providerId: String(provider.id),
          };
        }
      }
    }

    // LEGACY FORMAT: Try parsing with "__" separator
    const model = parseLlmDescriptor(modelName);
    // If we have no parsed modelName, try to find the provider by the raw modelName string
    if (!(model.modelName && model.modelName.length > 0)) {
      const provider = llmProviders.find((p) =>
        p.model_configurations
          .map((modelConfiguration) => modelConfiguration.name)
          .includes(modelName)
      );
      if (provider) {
        return {
          modelName: modelName,
          name: provider.name,
          provider: provider.provider,
          providerId: String(provider.id),
        };
      }
    }

    // If we have parsed provider info, try to find that specific provider.
    // This ensures we don't incorrectly match a model to the wrong provider
    // when the same model name exists across multiple providers (e.g., gpt-5 in Azure and OpenAI)
    if (model.provider && model.provider.length > 0) {
      const matchingProvider = llmProviders.find(
        (p) =>
          p.provider === model.provider &&
          p.model_configurations
            .map((modelConfiguration) => modelConfiguration.name)
            .includes(model.modelName)
      );
      if (matchingProvider) {
        return {
          ...model,
          name: matchingProvider.name,
          provider: matchingProvider.provider,
          providerId: String(matchingProvider.id),
        };
      }
      // Provider info was present but not found - fall through to default
    } else {
      // Only search by model name when no provider info was parsed
      const provider = llmProviders.find((p) =>
        p.model_configurations
          .map((modelConfiguration) => modelConfiguration.name)
          .includes(model.modelName)
      );

      if (provider) {
        return {
          ...model,
          provider: provider.provider,
          name: provider.name,
          providerId: String(provider.id),
        };
      }
    }
  }

  // Model not found in available providers - fall back to default model
  return (
    getDefaultLlmDescriptor(llmProviders) ?? {
      name: "",
      provider: "",
      modelName: "",
    }
  );
}

export function useLlmManager(
  currentChatSession?: ChatSession,
  liveAgent?: MinimalPersonaSnapshot
): LlmManager {
  const { user } = useUser();

  // Unified available-models endpoint already returns the complete provider/model list.
  const { llmProviders, isLoading: isLoadingProviders } = useAvailableModels();
  const defaultText: DefaultModel | null = null;

  const [userHasManuallyOverriddenLLM, setUserHasManuallyOverriddenLLM] =
    useState(false);
  const [chatSession, setChatSession] = useState<ChatSession | null>(null);
  const [currentLlm, setCurrentLlm] = useState<LlmDescriptor>({
    name: "",
    provider: "",
    modelName: "",
  });

  // Track the previous assistant ID to detect when it changes
  const prevAgentIdRef = useRef<string | number | undefined>(undefined);

  // Reset manual override when switching to a different assistant
  useEffect(() => {
    if (
      liveAgent?.id !== undefined &&
      prevAgentIdRef.current !== undefined &&
      liveAgent.id !== prevAgentIdRef.current
    ) {
      // User switched to a different assistant - reset manual override
      setUserHasManuallyOverriddenLLM(false);
    }
    prevAgentIdRef.current = liveAgent?.id;
  }, [liveAgent?.id]);

  const llmUpdate = () => {
    /* Should be called when the live assistant or current chat session changes */

    // Don't update if providers haven't loaded yet (undefined/null)
    // Empty arrays are valid (user has no provider access for this assistant)
    if (llmProviders === undefined || llmProviders === null) {
      return;
    }

    // separate function so we can `return` to break out
    const _llmUpdate = () => {
      // if the user has overridden in this session and just switched to a brand
      // new session, use their manually specified model
      if (userHasManuallyOverriddenLLM && !currentChatSession) {
        return;
      }

      if (currentChatSession?.current_alternate_model) {
        setCurrentLlm(
          getValidLlmDescriptor(currentChatSession.current_alternate_model)
        );
      } else if (liveAgent?.llm_model_version_override) {
        setCurrentLlm(
          getValidLlmDescriptor(liveAgent.llm_model_version_override)
        );
      } else if (userHasManuallyOverriddenLLM) {
        // if the user has an override and there's nothing special about the
        // current chat session, use the override
        return;
      } else if (user?.preferences?.default_model) {
        const defaultProviderId =
          user.preferences.default_provider_id ?? undefined;
        const resolved = getValidLlmDescriptor(user.preferences.default_model);
        if (defaultProviderId && resolved.modelName) {
          resolved.providerId = defaultProviderId;
          const matchedProvider = llmProviders?.find(
            (p) => String(p.id) === defaultProviderId
          );
          if (matchedProvider) {
            resolved.provider = matchedProvider.provider;
            resolved.name = matchedProvider.name;
          }
        }
        setCurrentLlm(resolved);
      } else {
        const defaultLlm = getDefaultLlmDescriptor(llmProviders, defaultText);
        if (defaultLlm) {
          setCurrentLlm(defaultLlm);
        }
      }
    };

    _llmUpdate();
    setChatSession(currentChatSession || null);
  };

  function getValidLlmDescriptor(
    modelName: string | null | undefined
  ): LlmDescriptor {
    return getValidLlmDescriptorForProviders(modelName, llmProviders);
  }

  const [imageFilesPresent, setImageFilesPresent] = useState(false);

  const updateImageFilesPresent = (present: boolean) => {
    setImageFilesPresent(present);
  };

  // Manually set the LLM
  const updateCurrentLlm = (newLlm: LlmDescriptor) => {
    setCurrentLlm(newLlm);
    setUserHasManuallyOverriddenLLM(true);
  };

  const updateCurrentLlmToModelName = (modelName: string) => {
    setCurrentLlm(getValidLlmDescriptor(modelName));
    setUserHasManuallyOverriddenLLM(true);
  };

  const updateModelOverrideBasedOnChatSession = (chatSession?: ChatSession) => {
    if (chatSession && chatSession.current_alternate_model?.length > 0) {
      setCurrentLlm(getValidLlmDescriptor(chatSession.current_alternate_model));
    }
  };

  const [temperature, setTemperature] = useState<number>(() => {
    if (currentChatSession?.current_temperature_override != null) {
      // Derive Anthropic check from chat session since currentLlm isn't populated yet
      const sessionModel = currentChatSession.current_alternate_model
        ? parseLlmDescriptor(currentChatSession.current_alternate_model)
        : null;
      const isAnthropicModel = sessionModel
        ? isAnthropic(sessionModel.provider, sessionModel.modelName)
        : false;
      return Math.min(
        currentChatSession.current_temperature_override,
        isAnthropicModel ? 1.0 : 2.0
      );
    } else if (liveAgent?.tools.some((tool) => tool.name === SEARCH_TOOL_ID)) {
      return 0;
    }
    return 0.5;
  });

  const maxTemperature = useMemo(() => {
    // Check currentLlm first, fall back to chat session model if currentLlm isn't populated
    if (currentLlm.provider) {
      return isAnthropic(currentLlm.provider, currentLlm.modelName) ? 1.0 : 2.0;
    }
    const sessionModel = currentChatSession?.current_alternate_model
      ? parseLlmDescriptor(currentChatSession.current_alternate_model)
      : null;
    if (sessionModel?.provider) {
      return isAnthropic(sessionModel.provider, sessionModel.modelName)
        ? 1.0
        : 2.0;
    }
    return 2.0; // Default max when no model info available
  }, [currentLlm, currentChatSession]);

  useEffect(() => {
    if (isAnthropic(currentLlm.provider, currentLlm.modelName)) {
      const newTemperature = Math.min(temperature, 1.0);
      setTemperature(newTemperature);
      if (chatSession?.id) {
        updateTemperatureOverrideForChatSession(chatSession.id, newTemperature);
      }
    }
  }, [currentLlm]);

  useEffect(() => {
    llmUpdate();

    if (!chatSession && currentChatSession) {
      if (temperature) {
        updateTemperatureOverrideForChatSession(
          currentChatSession.id,
          temperature
        );
      }
      return;
    }

    if (currentChatSession?.current_temperature_override) {
      setTemperature(currentChatSession.current_temperature_override);
    } else if (liveAgent?.tools.some((tool) => tool.name === SEARCH_TOOL_ID)) {
      setTemperature(0);
    } else {
      setTemperature(0.5);
    }
  }, [
    liveAgent,
    currentChatSession,
    llmProviders,
    user?.preferences?.default_model,
  ]);

  const updateTemperature = (temperature: number) => {
    const clampedTemp = isAnthropic(currentLlm.provider, currentLlm.modelName)
      ? Math.min(temperature, 1.0)
      : temperature;
    setTemperature(clampedTemp);
    if (chatSession) {
      updateTemperatureOverrideForChatSession(chatSession.id, clampedTemp);
    }
  };

  // Track if any provider exists for the current persona context.
  // Uses the persona-aware list so chat input reflects actual access,
  // falling back to the global list when no persona is selected.
  const hasAnyProvider = (llmProviders?.length ?? 0) > 0;

  return {
    updateModelOverrideBasedOnChatSession,
    currentLlm,
    updateCurrentLlm,
    temperature,
    updateTemperature,
    imageFilesPresent,
    updateImageFilesPresent,
    liveAgent: liveAgent ?? null,
    maxTemperature,
    llmProviders,
    isLoadingProviders,
    hasAnyProvider,
  };
}

export function useAvailableModels(): {
  llmProviders: LLMProviderDescriptor[] | undefined;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
} {
  const { hasPermission } = useUser();
  const canReadProviders = hasPermission("provider:read");
  const { data, error, mutate } = useSWR<LLMProviderDescriptor[]>(
    canReadProviders
      ? modelProvidersEndpoints.listAvailableModels.browserPath
      : null,
    () => fetchAvailableModels<LLMProviderDescriptor[]>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  return {
    llmProviders: canReadProviders ? data : EMPTY_LLM_PROVIDERS,
    isLoading: canReadProviders && !error && !data,
    error,
    refetch: () => {
      if (canReadProviders) void mutate();
    },
  };
}

/**
 * Fetches configured LLM providers accessible to the current user.
 *
 * Hits the **non-admin** endpoints which return `LLMProviderDescriptor`
 * (no `id` or sensitive fields like `api_key`). Use this hook in
 * user-facing UI (chat, popovers, onboarding) where you need the list
 * of providers and their visible models but don't need admin-level details.
 *
 * The backend wraps the provider list in an `LLMProviderResponse` envelope
 * that also carries the global default text and vision models. This hook
 * unwraps `.providers` for convenience while still exposing the defaults.
 *
 * **Endpoints:**
 * - No `personaId` → `GET /api/llm/provider`
 *   Returns all public providers plus restricted providers the user can
 *   access via group membership.
 * - With `personaId` → `GET /api/llm/persona/{personaId}/providers`
 *   Returns providers scoped to a specific persona, respecting RBAC
 *   restrictions. Use this when displaying model options for a particular
 *   assistant.
 *
 * @param personaId - Optional persona ID for RBAC-scoped providers.
 *
 * @returns
 * - `llmProviders` — The array of provider descriptors, or `undefined`
 *    while loading.
 * - `defaultText` — The global (or persona-overridden) default text model.
 * - `defaultVision` — The global (or persona-overridden) default vision model.
 * - `isLoading` — `true` until the first successful response or error.
 * - `error` — The SWR error object, if any.
 * - `refetch` — SWR `mutate` function to trigger a revalidation.
 */
interface UseLLMProvidersOptions {
  enabled?: boolean;
}

export function useLLMProviders(
  personaId?: number,
  options: UseLLMProvidersOptions = {}
) {
  const { hasPermission } = useUser();
  const canReadProviders = hasPermission("provider:read");
  const url =
    personaId !== undefined
      ? modelProvidersEndpoints.getPersonaProviders(personaId).browserPath
      : modelProvidersEndpoints.getProviderSelection.browserPath;
  const enabled = canReadProviders && (options.enabled ?? true);
  const { mutate: mutateKey } = useSWRConfig();

  const swrKey = enabled ? url : null;
  const fetcher = () =>
    personaId !== undefined
      ? fetchLLMPersonaProviders<LLMProviderResponse<LLMProviderDescriptor>>(
          personaId
        )
      : fetchLLMProviders<LLMProviderResponse<LLMProviderDescriptor>>();

  const { data, error, mutate } = useSWR<
    LLMProviderResponse<LLMProviderDescriptor>
  >(swrKey, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  return {
    llmProviders: canReadProviders ? data?.providers : EMPTY_LLM_PROVIDERS,
    defaultText: canReadProviders ? data?.default_text ?? null : null,
    defaultVision: canReadProviders ? data?.default_vision ?? null : null,
    isLoading: enabled && !error && !data,
    error,
    refetch: canReadProviders
      ? enabled
        ? mutate
        : () => mutateKey(url)
      : async () => undefined,
  };
}

/**
 * Fetches configured LLM providers via the **admin** endpoint.
 *
 * Hits `GET /api/admin/llm/provider` which returns `LLMProviderView` —
 * the full provider object including `id`, `api_key` (masked),
 * group/persona assignments, and all other admin-visible fields.
 *
 * Use this hook on admin pages (e.g. the LLM Configuration page) where
 * you need provider IDs for mutations (setting defaults, editing, deleting)
 * or need to display admin-only metadata. **Do not use in user-facing UI**
 * — use `useLLMProviders` instead.
 *
 * @returns
 * - `llmProviders` — The array of full provider views, or `undefined`
 *    while loading.
 * - `defaultText` — The global default text model.
 * - `defaultVision` — The global default vision model.
 * - `isLoading` — `true` until the first successful response or error.
 * - `error` — The SWR error object, if any.
 * - `refetch` — SWR `mutate` function to trigger a revalidation.
 */
export function useAdminLLMProviders() {
  const { data, error, mutate } = useSWR<LLMProviderResponse<LLMProviderView>>(
    modelProvidersEndpoints.getAdminProvider.browserPath,
    () => fetchAdminLLMProvider<LLMProviderResponse<LLMProviderView>>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  return {
    llmProviders: data?.providers,
    defaultText: data?.default_text ?? null,
    defaultVision: data?.default_vision ?? null,
    isLoading: !error && !data,
    error,
    refetch: mutate,
  };
}

/**
 * Fetches the catalog of well-known (built-in) LLM providers.
 *
 * Hits `GET /api/admin/llm/built-in/options` which returns the static
 * list of provider descriptors that Atlas ships with out of the box
 * (OpenAI, Anthropic, Vertex AI, Bedrock, Azure, Ollama, OpenRouter,
 * etc.). Each descriptor includes the provider's known models and the
 * recommended default model.
 *
 * Used primarily on the LLM Configuration page and onboarding flows
 * to show which providers are available to set up, and to pre-populate
 * model lists before the user has entered credentials.
 *
 * @returns
 * - `wellKnownLLMProviders` — The array of built-in provider descriptors,
 *    or `null` while loading.
 * - `isLoading` — `true` until the first successful response or error.
 * - `error` — The SWR error object, if any.
 * - `mutate` — SWR `mutate` function to trigger a revalidation.
 */
export function useWellKnownLLMProviders() {
  const {
    data: wellKnownLLMProviders,
    error,
    isLoading,
    mutate,
  } = useSWR<WellKnownLLMProviderDescriptor[]>(
    modelProvidersEndpoints.getBuiltInOptions.browserPath,
    () => fetchAdminLLMBuiltInOptions<WellKnownLLMProviderDescriptor[]>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  return {
    wellKnownLLMProviders: wellKnownLLMProviders ?? null,
    isLoading,
    error,
    mutate,
  };
}

export function useAllProviders() {
  const { data, error, isLoading, mutate } = useSWR<AllProvidersResponse>(
    modelProvidersEndpoints.listProviders.browserPath,
    () => fetchProviders<AllProvidersResponse>(),
    { revalidateOnFocus: false }
  );
  return {
    providers: data,
    isLoading,
    error,
    refetch: mutate,
  };
}

export function useUrlProviders() {
  const { data, error, isLoading, mutate } = useSWR<AllProvidersResponse>(
    modelProvidersEndpoints.listProviders.browserPath,
    () => fetchProviders<AllProvidersResponse>(),
    { revalidateOnFocus: false }
  );
  return {
    data: data?.url_providers ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useApiKeyProviders() {
  const { data, error, isLoading, mutate } = useSWR<AllProvidersResponse>(
    modelProvidersEndpoints.listProviders.browserPath,
    () => fetchProviders<AllProvidersResponse>(),
    { revalidateOnFocus: false }
  );
  return {
    data: data?.user_providers ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useWellKnownLangChainProviders() {
  const { data, error, isLoading, mutate } = useSWR<
    WellKnownLangChainProvider[]
  >(
    modelProvidersEndpoints.listWellKnownProviders.browserPath,
    () => fetchWellKnownProviders<WellKnownLangChainProvider[]>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  return {
    data: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useBuiltinOllamaStatus() {
  const { data, error, isLoading, mutate } = useSWR<BuiltinOllamaStatus>(
    modelProvidersEndpoints.getOllamaStatus.browserPath,
    () => fetchOllamaStatus<BuiltinOllamaStatus>(),
    { revalidateOnFocus: false }
  );
  return {
    data,
    isLoading,
    error,
    mutate,
  };
}

export function useBuiltinOllamaModels() {
  const { data, error, isLoading, mutate } = useSWR<OllamaModelResponse[]>(
    modelProvidersEndpoints.listOllamaModels.browserPath,
    () => fetchOllamaModels<OllamaModelResponse[]>(),
    { revalidateOnFocus: false }
  );
  return {
    data: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useDeleteBuiltinOllamaModel() {
  return useCallback(async (modelName: string) => {
    await deleteOllamaModel(modelName);
  }, []);
}

export function useReorderProviders() {
  return useCallback(async (orderedConfigIds: string[]) => {
    await reorderProviders(orderedConfigIds);
  }, []);
}

export function useUpdateProviderDefaultModel() {
  return useCallback(async (configId: string, model: string | null) => {
    await updateProviderDefaultModel(configId, model);
  }, []);
}

export function useLLMProviderOptions(options: { enabled?: boolean } = {}) {
  const { data, error, mutate } = useSWR<
    WellKnownLLMProviderDescriptor[] | undefined
  >(
    options.enabled === false ? null : "llm-provider-options",
    () => fetchAdminLLMBuiltInOptions<WellKnownLLMProviderDescriptor[]>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000, // Dedupe requests within 1 minute
    }
  );

  return {
    llmProviderOptions: data,
    isLoading: options.enabled !== false && !error && !data,
    error,
    refetch: mutate,
  };
}
