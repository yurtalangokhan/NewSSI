// Additional endpoints used by hooks (not in domain's primary API)

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const modelProvidersEndpoints = {
  getBuiltInOptions: {
    method: "GET",
    browserPath: "/api/admin/llm/built-in/options",
    backend: { service: "agent", path: "/api/v1/admin/llm/built-in/options" },
  },
  setDefaultModel: {
    method: "POST",
    browserPath: "/api/admin/llm/default",
    backend: { service: "agent", path: "/api/v1/admin/llm/default" },
  },
  getConfiguredOllamaModels: {
    method: "POST",
    browserPath: "/api/admin/llm/ollama/available-models",
    backend: {
      service: "agent",
      path: "/api/v1/admin/llm/ollama/available-models",
    },
  },
  testDefaultProvider: {
    method: "POST",
    browserPath: "/api/admin/llm/test/default",
    backend: { service: "agent", path: "/api/v1/admin/llm/test/default" },
  },
  testProvider: {
    method: "POST",
    browserPath: "/api/admin/llm/test",
    backend: { service: "agent", path: "/api/v1/admin/llm/test" },
  },
  listOllamaModels: {
    method: "GET",
    browserPath: "/api/admin/ollama/models",
    backend: { service: "agent", path: "/api/v1/admin/ollama/models" },
  },
  getOllamaStatus: {
    method: "GET",
    browserPath: "/api/admin/ollama/status",
    backend: { service: "agent", path: "/api/v1/admin/ollama/status" },
  },
  deleteOllamaModel: (modelName: string) =>
    ({
      method: "DELETE",
      browserPath: `/api/admin/ollama/models/${encodeURIComponent(modelName)}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/ollama/models/${modelName}`,
      },
    }) as const,
  listProviders: {
    method: "GET",
    browserPath: "/api/admin/providers",
    backend: { service: "agent", path: "/api/v1/admin/providers" },
  },
  createProvider: {
    method: "POST",
    browserPath: "/api/admin/providers",
    backend: { service: "agent", path: "/api/v1/admin/providers" },
  },
  deleteProvider: (id: string) =>
    ({
      method: "DELETE",
      browserPath: `/api/admin/providers/${id}`,
      backend: { service: "agent", path: `/api/v1/admin/providers/${id}` },
    }) as const,
  updateProvider: (id: string) =>
    ({
      method: "PUT",
      browserPath: `/api/admin/providers/${id}`,
      backend: { service: "agent", path: `/api/v1/admin/providers/${id}` },
    }) as const,
  listAvailableModels: {
    method: "GET",
    browserPath: "/api/admin/providers/available-models",
    backend: {
      service: "agent",
      path: "/api/v1/admin/providers/available-models",
    },
  },
  testProviderConnection: {
    method: "POST",
    browserPath: "/api/admin/providers/test-connection",
    backend: {
      service: "agent",
      path: "/api/v1/admin/providers/test-connection",
    },
  },
  listWellKnownProviders: {
    method: "GET",
    browserPath: "/api/admin/providers/well-known",
    backend: { service: "agent", path: "/api/v1/admin/providers/well-known" },
  },
  listUserProviders: {
    method: "GET",
    browserPath: "/api/admin/user-providers",
    backend: { service: "agent", path: "/api/v1/admin/user-providers" },
  },
  createUserProvider: {
    method: "POST",
    browserPath: "/api/admin/user-providers",
    backend: { service: "agent", path: "/api/v1/admin/user-providers" },
  },
  deleteUserProvider: (id: string) =>
    ({
      method: "DELETE",
      browserPath: `/api/admin/user-providers/${id}`,
      backend: { service: "agent", path: `/api/v1/admin/user-providers/${id}` },
    }) as const,
  updateUserProvider: (id: string) =>
    ({
      method: "PUT",
      browserPath: `/api/admin/user-providers/${id}`,
      backend: { service: "agent", path: `/api/v1/admin/user-providers/${id}` },
    }) as const,
  getPersonaProviders: (personaId: string | number) =>
    ({
      method: "GET",
      browserPath: `/api/llm/persona/${personaId}/providers`,
      backend: {
        service: "agent",
        path: `/api/v1/llm/persona/${personaId}/providers`,
      },
    }) as const,
  getProviderModels: (id: string) =>
    ({
      method: "GET",
      browserPath: `/api/admin/providers/${id}/models`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/providers/${id}/models`,
      },
    }) as const,
  syncProviderModels: (id: string) =>
    ({
      method: "POST",
      browserPath: `/api/admin/providers/${id}/sync-models`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/providers/${id}/sync-models`,
      },
    }) as const,
  getAdminProvider: {
    method: "GET",
    browserPath: "/api/admin/llm/provider",
    backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
  },
  updateAdminProvider: {
    method: "PUT",
    browserPath: "/api/admin/llm/provider",
    backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
  },
  createAdminProvider: {
    method: "POST",
    browserPath: "/api/admin/llm/provider",
    backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
  },
  getProviderSelection: {
    method: "GET",
    browserPath: "/api/llm/provider",
    backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
  },
  pullOllamaModel: {
    method: "POST",
    browserPath: "/api/admin/ollama/pull",
    backend: { service: "agent", path: "/api/v1/admin/ollama/pull" },
  },
  providerOrder: { browserPath: "/api/admin/providers/order" },
  llmPersonaProviders: { browserPath: "/api/llm/persona" },
  adminLlmProviderWithImageGen: {
    browserPath: "/api/admin/llm/provider?include_image_gen=true",
  },
  adminLlmBuiltInProvider: (provider: string): { browserPath: string } => {
    return {
      browserPath: `${
        modelProvidersEndpoints.getBuiltInOptions.browserPath
      }/${encodeURIComponent(provider)}`,
    };
  },
  providerDefaultModel: (configId: string): { browserPath: string } => {
    return {
      browserPath: `${
        modelProvidersEndpoints.listProviders.browserPath
      }/${encodeURIComponent(configId)}/default-model`,
    };
  },
  llmAdmin: { browserPath: "/api/admin/llm" },
  deleteLlmProvider: (providerId: number): { browserPath: string } => {
    return {
      browserPath: `${modelProvidersEndpoints.getAdminProvider.browserPath}/${providerId}`,
    };
  },
  imageGenTest: { browserPath: "/api/admin/image-generation/test" },
  imageGenConfig: { browserPath: "/api/admin/image-generation/config" },
  fetchImageGenerationCredentials: (
    imageProviderId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${modelProvidersEndpoints.imageGenConfig.browserPath}/${imageProviderId}/credentials`,
    };
  },
  updateImageGenerationConfig: (
    imageProviderId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${modelProvidersEndpoints.imageGenConfig.browserPath}/${imageProviderId}`,
    };
  },
  setDefaultImageGenerationConfig: (
    imageProviderId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${modelProvidersEndpoints.imageGenConfig.browserPath}/${imageProviderId}/default`,
    };
  },
  fetchBedrockModels: {
    browserPath: "/api/admin/llm/bedrock/available-models",
  },
  fetchOpenRouterModels: {
    browserPath: "/api/admin/llm/openrouter/available-models",
  },
  createBuildOnboardingProvider: {
    browserPath: "/api/admin/llm/provider?is_creation=true",
  },
  saveProviderFormConfiguration: (
    pathValue: "" | "?is_creation=true"
  ): { browserPath: string } => {
    return { browserPath: `${"/api/admin/llm/provider"}${pathValue}` };
  },
  setBuildProviderDefault: (id: number): { browserPath: string } => {
    return { browserPath: `${"/api/admin/llm/provider"}/${id}/default` };
  },
  llmContextualCost: { browserPath: "/api/admin/llm/provider-contextual-cost" },
} as const;
