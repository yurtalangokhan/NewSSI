import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

import {
  ProviderTestPayload,
  ProviderUpsertPayload,
} from "@/lib/api/domains/knowledge/provider-types";
import { testWebProvider } from "@/lib/api/domains/knowledge/api";
import { upsertWebProvider } from "@/lib/api/domains/knowledge/api";

const WEB_SEARCH_PROVIDER_ENDPOINTS = {
  search: {
    upsertUrl: knowledgeEndpoints.searchProviders.browserPath,
    testUrl: knowledgeEndpoints.searchProviderTest.browserPath,
  },
  content: {
    upsertUrl: knowledgeEndpoints.createContentProvider.browserPath,
    testUrl: knowledgeEndpoints.contentProviderTest.browserPath,
  },
} as const;

/**
 * Which web-search provider category we are configuring.
 * - `search`: search engine provider
 * - `content`: crawler/content provider used to fetch full pages
 */
export type WebProviderCategory = keyof typeof WEB_SEARCH_PROVIDER_ENDPOINTS;

export type ConnectProviderFlowArgs = {
  category: WebProviderCategory;
  providerType: string;

  existingProviderId: number | null;
  existingProviderName: string | null;
  existingProviderHasApiKey: boolean;

  displayName: string;

  providerRequiresApiKey: boolean;
  apiKeyChangedForProvider: boolean;
  apiKey: string;

  config: Record<string, string>;
  configChanged: boolean;

  onValidating: (message: string) => void;
  onSaving: (message: string) => void;
  onError: (message: string) => void;
  onClose: () => void;

  mutate: () => Promise<unknown>;
};

export async function connectProviderFlow({
  category,
  providerType,
  existingProviderId,
  existingProviderName,
  existingProviderHasApiKey,
  displayName,
  providerRequiresApiKey,
  apiKeyChangedForProvider,
  apiKey,
  config,
  configChanged,
  onValidating,
  onSaving,
  onError,
  onClose,
  mutate,
}: ConnectProviderFlowArgs): Promise<void> {
  const { testUrl, upsertUrl } = WEB_SEARCH_PROVIDER_ENDPOINTS[category];
  const isNewProvider = existingProviderId == null;
  const needsValidation =
    isNewProvider || apiKeyChangedForProvider || configChanged;
  const msg = {
    validating: "Validating configuration...",
    activating: "Activating provider...",
    validatedThenActivating: "Configuration validated. Activating provider...",
    validationFailedFallback: "Failed to validate configuration.",
    activateFailedFallback: "Failed to activate provider.",
  };

  if (providerRequiresApiKey) {
    if (isNewProvider && !apiKey) {
      return;
    }
    if (apiKeyChangedForProvider && !apiKey) {
      return;
    }
  }

  try {
    if (needsValidation) {
      onValidating(msg.validating);

      const testPayload: ProviderTestPayload = {
        provider_type: providerType,
        api_key: apiKeyChangedForProvider ? apiKey : null,
        use_stored_key:
          providerRequiresApiKey &&
          !apiKeyChangedForProvider &&
          existingProviderHasApiKey,
        config,
      };

      const testResponse = await testWebProvider(category, testPayload);

      if (!testResponse.ok) {
        const errorBody = await testResponse.json().catch(() => ({}));
        throw new Error(
          typeof (errorBody as any)?.detail === "string"
            ? (errorBody as any).detail
            : msg.validationFailedFallback
        );
      }

      onSaving(msg.validatedThenActivating);
    } else {
      onSaving(msg.activating);
    }

    const upsertPayload: ProviderUpsertPayload = {
      id: existingProviderId,
      name: existingProviderName ?? displayName,
      provider_type: providerType,
      api_key: apiKeyChangedForProvider ? apiKey : null,
      api_key_changed: apiKeyChangedForProvider,
      config,
      activate: true,
    };

    const upsertResponse = await upsertWebProvider(category, upsertPayload);

    if (!upsertResponse.ok) {
      const errorBody = await upsertResponse.json().catch(() => ({}));
      throw new Error(
        typeof (errorBody as any)?.detail === "string"
          ? (errorBody as any).detail
          : msg.activateFailedFallback
      );
    }

    await mutate();
    onClose();
  } catch (e) {
    const message =
      e instanceof Error ? e.message : "Unexpected error occurred.";
    onError(message);
  }
}
