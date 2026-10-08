import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import type { ApiRequestOptions } from "@/lib/api/http/types";
import { userServicePayloadResponse } from "@/lib/api/userServiceResponse";
import { parseResponseModel } from "@/lib/api/responseModel";
import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";
import { ThemePreference, UserSpecificAgentPreferences } from "@/lib/types";
import i18n from "@/i18n/config";

/**
 * Fetch assistant preferences, throwing FetchError on non-OK.
 * Used by SWR hooks that rely on thrown errors for error state.
 */
export async function fetchAssistantPreferencesWithError(): Promise<UserSpecificAgentPreferences> {
  const res = await apiRequest(
    preferencesEndpoints.getAssistantPreferences().browserPath
  );
  if (!res.ok) {
    const parsedError = await parseApiErrorResponse(res);
    throw new FetchError(
      parsedError.userMessage,
      res.status,
      parsedError.raw,
      parsedError
    );
  }
  const data = await parseJsonResponse<UserSpecificAgentPreferences>(res);
  return data ?? ({} as UserSpecificAgentPreferences);
}

export async function updateAgentPreferences(
  agentId: number,
  prefs: unknown
): Promise<unknown> {
  const res = await apiRequest(
    preferencesEndpoints.agentPreferences(agentId).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    }
  );
  return (await parseJsonResponse<unknown>(res)) ?? {};
}

export function updateThemePreference(
  themePreference: ThemePreference
): Promise<Record<string, unknown>> {
  return requestSettingsData(preferencesEndpoints.themePreference.browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme_preference: themePreference }),
  });
}

export function updateChatBackground(
  chatBackground: string | null
): Promise<Record<string, unknown>> {
  return requestSettingsData(preferencesEndpoints.chatBackground.browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_background: chatBackground }),
  });
}

export function updateDefaultModel(
  defaultModel: string | null,
  defaultProviderId?: string | null
): Promise<Record<string, unknown>> {
  return requestSettingsData(preferencesEndpoints.defaultModel.browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      default_model: defaultModel,
      ...(defaultProviderId !== undefined && {
        default_provider_id: defaultProviderId,
      }),
    }),
  });
}

export function updateDefaultAppMode(
  mode: "CHAT" | "SEARCH"
): Promise<Record<string, unknown>> {
  return requestSettingsData(preferencesEndpoints.defaultAppMode.browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_app_mode: mode }),
  });
}

/**
 * Update personalization and unwrap the standard response data.
 */
export async function updatePersonalization(
  personalization: unknown
): Promise<Record<string, unknown>> {
  return requestSettingsData(
    preferencesEndpoints.updatePersonalizationProfile.browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(personalization),
    }
  );
}

export function fetchMemories(
  page: number,
  pageSize: number
): Promise<Response> {
  return requestMemoryResponse(
    preferencesEndpoints.memoriesPage(page, pageSize).browserPath
  );
}

export function createMemory(content: string): Promise<Response> {
  return requestMemoryResponse(preferencesEndpoints.createMemory.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export function updateMemory(id: string, content: string): Promise<Response> {
  return requestMemoryResponse(
    preferencesEndpoints.updateMemory(id).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }
  );
}

export function deleteMemory(id: string): Promise<Response> {
  return requestMemoryResponse(
    preferencesEndpoints.deleteMemory(id).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function deleteAllMemories(): Promise<Response> {
  return requestMemoryResponse(
    preferencesEndpoints.deleteAllMemories.browserPath,
    {
      method: "DELETE",
    }
  );
}

export async function fetchInputPrompts<T = unknown[]>(): Promise<T> {
  const res = await apiRequest(
    preferencesEndpoints.getInputPrompts.browserPath
  );
  return parseResponseModel<T>(res);
}

export function updatePinnedAssistants(
  ids: number[]
): Promise<Record<string, unknown>> {
  return requestSettingsData(
    preferencesEndpoints.updatePinnedAssistants.browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordered_assistant_ids: ids }),
    }
  );
}

export function updateTemperatureOverrideEnabled(
  enabled: boolean
): Promise<Response> {
  return apiRequest(
    preferencesEndpoints.temperatureOverride(enabled).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
    }
  );
}

export function updateShortcutEnabled(
  enabled: boolean
): Promise<Record<string, unknown>> {
  return requestSettingsData(
    preferencesEndpoints.updateShortcutEnabled(enabled).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
    }
  );
}

export function updateAutoScroll(
  autoScroll: boolean
): Promise<Record<string, unknown>> {
  return requestSettingsData(preferencesEndpoints.autoScroll.browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auto_scroll: autoScroll }),
  });
}

export function updateDefaultAssistantTools(payload: {
  tool_ids: number[];
}): Promise<Response> {
  return apiRequest(
    preferencesEndpoints.updateDefaultAssistantTools.browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function updateAdminChatSettings(payload: {
  anonymous_user_enabled: boolean;
  invite_only_enabled: boolean;
  anonymous_user_path?: string | undefined;
  maximum_chat_retention_days?: number | null | undefined;
  company_name?: string | null | undefined;
  company_description?: string | null | undefined;
  notifications: import("@/interfaces/settings").Notification[];
  needs_reindexing: boolean;
  gpu_enabled: boolean;
  application_status: import("@/interfaces/settings").ApplicationStatus;
  auto_scroll: boolean;
  temperature_override_enabled: boolean;
  query_history_type: import("@/interfaces/settings").QueryHistoryType;
  deep_research_enabled?: boolean | undefined;
  search_ui_enabled?: boolean | undefined;
  image_extraction_and_analysis_enabled?: boolean | undefined;
  search_time_image_analysis_enabled?: boolean | undefined;
  image_analysis_max_size_mb?: number | null | undefined;
  user_knowledge_enabled?: boolean | undefined;
  show_extra_connectors?: boolean | undefined;
  disable_default_assistant?: boolean | undefined;
  atlas_craft_enabled?: boolean | undefined;
  ee_features_enabled?: boolean | undefined;
  seat_count?: number | null | undefined;
  used_seats?: number | null | undefined;
  opensearch_indexing_enabled?: boolean | undefined;
  vector_db_enabled?: boolean | undefined;
}): Promise<Response> {
  return apiRequest(preferencesEndpoints.updateAdminChatSettings.browserPath, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateDefaultAssistantPreferences(payload: {
  system_prompt: string;
}): Promise<Response> {
  return apiRequest(
    preferencesEndpoints.updateDefaultAssistantTools.browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function deleteInputShortcut(
  id: number
): Promise<Record<string, unknown>> {
  return requestSettingsData(
    preferencesEndpoints.deleteInputPrompt(id).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function createInputShortcut(payload: {
  prompt: string;
  content: string;
  active: boolean;
  is_public: boolean;
}): Promise<Record<string, unknown>> {
  return requestSettingsData(
    preferencesEndpoints.createInputPrompt.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function updateInputShortcut(
  id: number,
  payload: {
    prompt: string;
    content: string;
    active: boolean;
    is_public: boolean;
  }
): Promise<Record<string, unknown>> {
  return requestSettingsData(
    preferencesEndpoints.updateInputPrompt(id).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}
export async function fetchDefaultAssistantConfiguration<T>(): Promise<T> {
  const response = await apiRequest(
    preferencesEndpoints.defaultAssistantConfiguration.browserPath,
    {
      headers: { "X-Language": i18n.language },
    }
  ).then(agentServicePayloadResponse);
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

async function requestSettingsData<T = Record<string, unknown>>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  return parseResponseModel<T>(await apiRequest(path, options));
}

async function requestMemoryResponse(
  path: string,
  options: ApiRequestOptions = {}
): Promise<Response> {
  return userServicePayloadResponse(await apiRequest(path, options));
}
