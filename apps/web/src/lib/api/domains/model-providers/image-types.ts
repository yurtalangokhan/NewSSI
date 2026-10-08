export interface ImageGenerationConfigView {
  image_provider_id: string; // Primary key
  model_configuration_id: number;
  model_name: string;
  llm_provider_id: number;
  llm_provider_name: string;
  is_default: boolean;
}

export interface TestApiKeyResult {
  ok: boolean;
  errorMessage?: string;
}

export interface ImageGenerationCredentials {
  api_key: string | null;
  api_base: string | null;
  api_version: string | null;
  deployment_name: string | null;
  custom_config: Record<string, string> | null;
}

export interface ImageGenerationConfigCreateOptions {
  imageProviderId: string;
  modelName: string;
  isDefault?: boolean;

  // Option 1: Clone mode - use credentials from existing provider
  sourceLlmProviderId?: number;

  // Option 2: New credentials mode
  provider?: string;
  apiKey?: string;
  apiBase?: string;
  apiVersion?: string;
  deploymentName?: string;
  customConfig?: Record<string, string>;
}

export interface ImageGenerationConfigUpdateOptions {
  modelName: string;

  // Option 1: Clone mode - use credentials from existing provider
  sourceLlmProviderId?: number;

  // Option 2: New credentials mode
  provider?: string;
  apiKey?: string;
  apiBase?: string;
  apiVersion?: string;
  deploymentName?: string;
  customConfig?: Record<string, string>;

  // If true, apiKey was changed by user; if false, backend preserves existing key
  apiKeyChanged?: boolean;
}
