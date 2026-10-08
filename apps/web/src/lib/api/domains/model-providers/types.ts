import type { LLMProviderName, ModelConfiguration } from "@/interfaces/llm";

export interface BaseLLMFormValues {
  name: string;
  api_key?: string;
  api_base?: string;
  default_model_name?: string;
  is_public: boolean;
  is_auto_mode: boolean;
  groups: number[];
  personas: number[];
  selected_model_names: string[];
  custom_config?: Record<string, string>;
}

export type ProviderFormTestPayload<T extends BaseLLMFormValues> = {
  provider: string;
} & Omit<T, "selected_model_names" | "api_key"> & {
    model: T["default_model_name"] | undefined;
    id: number | undefined;
    api_base: T["api_base"] | undefined;
    default_model_name: T["default_model_name"] | undefined;
    api_key: string | undefined;
    api_key_changed: boolean;
    custom_config_changed: boolean;
    model_configurations: ModelConfiguration[];
  };

export type ProviderFormSavePayload<T extends BaseLLMFormValues> = {
  provider: string;
} & Omit<T, "selected_model_names" | "api_key"> & {
    id: number | undefined;
    api_base: T["api_base"] | undefined;
    default_model_name: T["default_model_name"] | undefined;
    api_key: string | undefined;
    api_key_changed: boolean;
    custom_config_changed: boolean;
    model_configurations: ModelConfiguration[];
  };

export interface OnboardingProviderTestPayload {
  provider: string;
  api_key?: string;
  api_base?: string;
  api_version?: string;
  deployment_name?: string;
  api_key_changed: boolean;
  custom_config_changed: boolean;
  custom_config?: Record<string, string>;
  model?: string;
}

export interface ProviderConfigurationPayload {
  name: string;
  provider: LLMProviderName | string;
  api_key: string;
  default_model_name: string;
  model_configurations: ProviderConfigurationModel[];
  api_base: string;
  api_version: string;
  custom_config: Record<string, string>;
  api_key_changed: boolean;
  groups: number[];
  is_public: boolean;
  deployment_name: string;
  target_uri: string;
  is_auto_mode?: boolean;
  personas?: number[];
}

export interface ProviderConfigurationModel {
  name: string;
  is_visible: boolean;
  max_input_tokens: number | null;
  supports_image_input: boolean;
  supports_reasoning?: boolean;
  display_name?: string;
}

export interface ProviderDefaultPayload {
  provider_id: number;
  model_name: string | undefined;
}
