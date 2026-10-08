import { ApiRequestError, errorMessageFromUnknown } from "@/lib/api/errors";
import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";

import { parseResponseModel } from "@/lib/api/responseModel";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

import type {
  BaseLLMFormValues,
  OnboardingProviderTestPayload,
  ProviderConfigurationPayload,
  ProviderDefaultPayload,
  ProviderFormSavePayload,
  ProviderFormTestPayload,
} from "@/lib/api/domains/model-providers/types";

async function fetchAgentProviderJson<T>(path: string): Promise<T> {
  return apiRequest(path, {
    headers: { "X-Language": i18n.language },
  }).then(parseResponseModel<T>);
}

async function fetchProviderSWRJson<T>(path: string): Promise<T> {
  const response = await apiRequest(path, {
    headers: { "X-Language": i18n.language },
  });
  if (!response.ok) {
    const parsedError = await parseApiErrorResponse(response);
    throw new FetchError(
      parsedError.userMessage,
      response.status,
      parsedError.raw,
      parsedError
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    return {} as T;
  }
}

export const fetchLLMContextualCosts = <T>() =>
  fetchProviderSWRJson<T>(
    modelProvidersEndpoints.llmContextualCost.browserPath
  );

export function fetchProviders<T = unknown[]>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.listProviders.browserPath
  );
}

export function fetchAvailableModels<T = unknown[]>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.listAvailableModels.browserPath
  );
}

export function fetchWellKnownProviders<T = unknown[]>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.listWellKnownProviders.browserPath
  );
}

export function fetchLLMProviders<T = unknown[]>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.getProviderSelection.browserPath
  );
}

export function fetchLLMPersonaProviders<T = unknown[]>(
  personaId: number
): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.getPersonaProviders(personaId).browserPath
  );
}

export function fetchAdminLLMProvider<T = unknown[]>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.getAdminProvider.browserPath
  );
}

export function fetchAdminLLMBuiltInOptions<T = unknown[]>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.getBuiltInOptions.browserPath
  );
}

export function fetchWellKnownProvider<T>(provider: string): Promise<T> {
  return fetchProviderSWRJson<T>(
    modelProvidersEndpoints.adminLlmBuiltInProvider(provider).browserPath
  );
}

export function fetchAdminLLMProviderWithImageGen<T>(): Promise<T> {
  return fetchAgentProviderJson<T>(
    modelProvidersEndpoints.adminLlmProviderWithImageGen.browserPath
  );
}

export function fetchOllamaStatus<T = unknown>(): Promise<T> {
  return apiRequest(modelProvidersEndpoints.getOllamaStatus.browserPath, {
    headers: { "X-Language": i18n.language },
  }).then(parseResponseModel<T>);
}

export function fetchOllamaModels<T = unknown[]>(): Promise<T> {
  return apiRequest(modelProvidersEndpoints.listOllamaModels.browserPath, {
    headers: { "X-Language": i18n.language },
  }).then(parseResponseModel<T>);
}

export async function deleteOllamaModel(modelName: string): Promise<void> {
  const res = await apiRequest(
    modelProvidersEndpoints.deleteOllamaModel(modelName).browserPath,
    {
      method: "DELETE",
    }
  );
  await parseResponseModel<unknown>(res);
}

export async function reorderProviders(
  orderedConfigIds: string[]
): Promise<void> {
  const res = await apiRequest(
    modelProvidersEndpoints.providerOrder.browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordered_config_ids: orderedConfigIds }),
    }
  ).then(agentServicePayloadResponse);
  if (!res.ok) {
    throw new FetchError(
      `Failed to reorder providers: ${res.statusText}`,
      res.status,
      res
    );
  }
}

export async function updateProviderDefaultModel(
  configId: string,
  model: string | null
): Promise<void> {
  const res = await apiRequest(
    modelProvidersEndpoints.providerDefaultModel(configId).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    }
  ).then(agentServicePayloadResponse);
  if (!res.ok) {
    throw new FetchError(
      `Failed to update provider default model: ${res.statusText}`,
      res.status,
      res
    );
  }
}

import { getErrorMsg } from "@/lib/fetchUtils";

export async function testDefaultProvider(): Promise<boolean> {
  try {
    const response = await apiRequest(
      modelProvidersEndpoints.testDefaultProvider.browserPath,
      {
        method: "POST",
      }
    ).then(agentServicePayloadResponse);
    return response?.ok || false;
  } catch {
    return false;
  }
}

export async function setDefaultLlmModel(
  providerId: number,
  modelName: string
): Promise<void> {
  const response = await apiRequest(
    modelProvidersEndpoints.setDefaultModel.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider_id: providerId,
        model_name: modelName,
      }),
    }
  ).then(agentServicePayloadResponse);

  if (!response.ok) {
    const errorMsg = (await getErrorMsg(response)) ?? "Unknown error";
    throw new Error(errorMsg);
  }
}

export async function deleteLlmProvider(providerId: number): Promise<void> {
  const response = await apiRequest(
    modelProvidersEndpoints.deleteLlmProvider(providerId).browserPath,
    {
      method: "DELETE",
    }
  ).then(agentServicePayloadResponse);

  if (!response.ok) {
    const errorMsg = (await getErrorMsg(response)) ?? "Unknown error";
    throw new Error(errorMsg);
  }
}

import "@/lib/api/domains/model-providers/endpoints";

import {
  TestApiKeyResult,
  ImageGenerationConfigView,
  ImageGenerationCredentials,
  ImageGenerationConfigCreateOptions,
  ImageGenerationConfigUpdateOptions,
} from "@/lib/api/domains/model-providers/image-types";

export async function testImageGenerationApiKey(
  modelName: string,
  options: {
    // Option 1: Direct API key
    provider?: string;
    apiKey?: string;
    // Option 2: Use existing provider
    sourceLlmProviderId?: number;
    // Additional fields
    apiBase?: string;
    apiVersion?: string;
    deploymentName?: string;
    customConfig?: Record<string, string>;
  }
): Promise<TestApiKeyResult> {
  try {
    const response = await apiRequest(
      modelProvidersEndpoints.imageGenTest.browserPath,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_name: modelName,
          provider: options.provider || null,
          api_key: options.apiKey || null,
          source_llm_provider_id: options.sourceLlmProviderId || null,
          api_base: options.apiBase || null,
          api_version: options.apiVersion || null,
          deployment_name: options.deploymentName || null,
          custom_config: options.customConfig || null,
        }),
      }
    );

    if (!response.ok) {
      return {
        ok: false,
        errorMessage: (await parseApiErrorResponse(response)).userMessage,
      };
    }

    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      errorMessage: errorMessageFromUnknown(error),
    };
  }
}

export async function fetchImageGenerationConfigs(): Promise<
  ImageGenerationConfigView[]
> {
  const response = await apiRequest(
    modelProvidersEndpoints.imageGenConfig.browserPath
  );
  if (!response.ok) {
    throw new Error("Failed to fetch image generation configs");
  }
  return parseJsonResponse<ImageGenerationConfigView[]>(response) as Promise<
    ImageGenerationConfigView[]
  >;
}

export async function fetchImageGenerationCredentials(
  imageProviderId: string
): Promise<ImageGenerationCredentials> {
  const response = await apiRequest(
    modelProvidersEndpoints.fetchImageGenerationCredentials(imageProviderId)
      .browserPath
  );
  if (!response.ok) {
    throw new Error("Failed to fetch credentials");
  }
  return parseJsonResponse<ImageGenerationCredentials>(
    response
  ) as Promise<ImageGenerationCredentials>;
}

export async function createImageGenerationConfig(
  options: ImageGenerationConfigCreateOptions
): Promise<ImageGenerationConfigView> {
  const response = await apiRequest(
    modelProvidersEndpoints.imageGenConfig.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_provider_id: options.imageProviderId,
        model_name: options.modelName,
        is_default: options.isDefault ?? false,
        // Clone mode
        source_llm_provider_id: options.sourceLlmProviderId,
        // New credentials mode
        provider: options.provider,
        api_key: options.apiKey,
        api_base: options.apiBase,
        api_version: options.apiVersion,
        deployment_name: options.deploymentName,
        custom_config: options.customConfig,
      }),
    }
  );

  if (!response.ok) {
    throw new ApiRequestError(await parseApiErrorResponse(response));
  }

  return parseJsonResponse<ImageGenerationConfigView>(
    response
  ) as Promise<ImageGenerationConfigView>;
}

export async function updateImageGenerationConfig(
  imageProviderId: string,
  options: ImageGenerationConfigUpdateOptions
): Promise<ImageGenerationConfigView> {
  const response = await apiRequest(
    modelProvidersEndpoints.updateImageGenerationConfig(imageProviderId)
      .browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_name: options.modelName,
        // Clone mode
        source_llm_provider_id: options.sourceLlmProviderId,
        // New credentials mode
        provider: options.provider,
        api_key: options.apiKey,
        api_base: options.apiBase,
        api_version: options.apiVersion,
        deployment_name: options.deploymentName,
        custom_config: options.customConfig,
        // If false, backend preserves existing API key
        api_key_changed: options.apiKeyChanged ?? false,
      }),
    }
  );

  if (!response.ok) {
    throw new ApiRequestError(await parseApiErrorResponse(response));
  }

  return parseJsonResponse<ImageGenerationConfigView>(
    response
  ) as Promise<ImageGenerationConfigView>;
}

export async function setDefaultImageGenerationConfig(
  imageProviderId: string
): Promise<void> {
  const response = await apiRequest(
    modelProvidersEndpoints.setDefaultImageGenerationConfig(imageProviderId)
      .browserPath,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    throw new ApiRequestError(await parseApiErrorResponse(response));
  }
}

export async function unsetDefaultImageGenerationConfig(
  imageProviderId: string
): Promise<void> {
  const response = await apiRequest(
    modelProvidersEndpoints.setDefaultImageGenerationConfig(imageProviderId)
      .browserPath,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    throw new ApiRequestError(await parseApiErrorResponse(response));
  }
}

export function deleteUserLlmProvider(id: string): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.deleteUserProvider(id).browserPath,
    {
      method: "DELETE",
    }
  ).then(agentServicePayloadResponse);
}

export function testUrlProviderConnection(payload: {
  provider_type: "ollama" | "vllm" | "openai_compatible" | "litellm";
  base_url: string;
  provider_id: string;
}): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.testProviderConnection.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function fetchUrlProviderModels(id: string): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.getProviderModels(id).browserPath
  ).then(agentServicePayloadResponse);
}

export function syncUrlProviderModels(id: string): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.syncProviderModels(id).browserPath,
    { method: "POST" }
  ).then(agentServicePayloadResponse);
}

export function deleteUrlProvider(id: string): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.deleteProvider(id).browserPath, {
    method: "DELETE",
  }).then(agentServicePayloadResponse);
}

export function testApiKeyProviderConnection(payload: {
  provider_type: string;
  api_key: string;
  base_url: string | undefined;
}): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.testProviderConnection.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function createApiKeyUserProvider(payload: {
  name: string;
  provider_type: string;
  api_key: string;
  api_base: string | undefined;
  api_version: string | undefined;
  default_model: string | undefined;
}): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.createUserProvider.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function testEditedProviderConnection(payload: {
  provider_type: string;
  base_url: string | undefined;
  api_key: string | undefined;
  provider_id: string | undefined;
}): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.testProviderConnection.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function updateSharedUrlProvider(
  id: string,
  payload: Record<string, unknown>
): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.updateProvider(id).browserPath, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function updatePersonalUrlProvider(
  id: string,
  payload: Record<string, string | null>
): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.updateUserProvider(id).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function pullOllamaModel(payload: {
  model: string;
  provider_id: string;
}): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.pullOllamaModel.browserPath, {
    method: modelProvidersEndpoints.pullOllamaModel.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function testNewUrlProviderConnection(payload: {
  provider_type: string;
  base_url: string;
  api_key: string | undefined;
}): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.testProviderConnection.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function createSharedUrlProvider(payload: {
  name: string;
  provider_type: string;
  base_url: string;
  api_key: string | undefined;
  default_model: string | undefined;
  config: { api_version: string | null; custom_config: Record<string, string> };
}): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.createProvider.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

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
import i18n from "@/i18n/config";

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
    const response = await apiRequest(
      modelProvidersEndpoints.fetchBedrockModels.browserPath,
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

export const fetchConfiguredOllamaModels = async (
  params: OllamaFetchParams
): Promise<{ models: ModelConfiguration[]; error?: string }> => {
  const apiBase = params.api_base;
  if (!apiBase) {
    return {
      models: [],
      error: i18n.t("llmOnboarding.apiBaseRequiredError"),
    };
  }

  try {
    const response = await apiRequest(
      modelProvidersEndpoints.getConfiguredOllamaModels.browserPath,
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
    ).then(agentServicePayloadResponse);

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

export const fetchOpenRouterModels = async (
  params: OpenRouterFetchParams
): Promise<{ models: ModelConfiguration[]; error?: string }> => {
  const apiBase = params.api_base;
  const apiKey = params.api_key;
  if (!apiBase) {
    return {
      models: [],
      error: i18n.t("llmOnboarding.apiBaseRequiredError"),
    };
  }
  if (!apiKey) {
    return {
      models: [],
      error: i18n.t("llmOnboarding.apiKeyRequiredError"),
    };
  }

  try {
    const response = await apiRequest(
      modelProvidersEndpoints.fetchOpenRouterModels.browserPath,
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
      return fetchConfiguredOllamaModels({
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
        error: i18n.t("llmOnboarding.unknownProvider", {
          providerName,
        }),
      };
  }
};

export function createProviderConfiguration(
  payload: ProviderConfigurationPayload
): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.createBuildOnboardingProvider.browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function testProviderConfiguration<T extends BaseLLMFormValues>(
  payload: ProviderFormTestPayload<T> | OnboardingProviderTestPayload
): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.testProvider.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function saveProviderFormConfiguration<T extends BaseLLMFormValues>(
  pathValue: "" | "?is_creation=true",
  payload: ProviderFormSavePayload<T>
): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.saveProviderFormConfiguration(pathValue)
      .browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function setProviderDefault(
  payload: ProviderDefaultPayload
): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.setDefaultModel.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function fetchOpenRouterFormModels(payload: {
  api_base: string;
  api_key: string;
  provider_name: string | undefined;
}): Promise<Response> {
  return apiRequest(modelProvidersEndpoints.fetchOpenRouterModels.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function setBuildProviderDefault(id: number): Promise<Response> {
  return apiRequest(
    modelProvidersEndpoints.setBuildProviderDefault(id).browserPath,
    {
      method: "POST",
    }
  ).then(agentServicePayloadResponse);
}
