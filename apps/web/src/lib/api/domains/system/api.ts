import { parseResponseModel } from "@/lib/api/responseModel";
import type { ApiRequestOptions } from "@/lib/api/http/types";
import { userServicePayloadResponse } from "@/lib/api/userServiceResponse";
import { systemEndpoints } from "@/lib/api/domains/system/endpoints";

/**
 * System Domain API client
 * Merged from system and performance modules.
 * Uses apiRequest from the shared browser transport.
 */

import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

import "@/lib/api/domains/model-providers/endpoints";

// Helper to make JSON requests through apiRequest
async function requestSystemJson<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const res = await apiRequest(path, options);
  if (!res.ok) {
    throw new Error(`System API request failed (Status: ${res.status})`);
  }
  const result = await parseJsonResponse<T>(res);
  if (result === undefined) {
    throw new Error("System API request returned empty response");
  }
  return result;
}

async function fetchSystemSWRJson<T>(path: string): Promise<T> {
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

export const fetchLogCategoryList = <T>() =>
  fetchSystemSWRJson<T>(systemEndpoints.fetchLogCategories.browserPath);

export const fetchAdminQueryAnalytics = <T>(start?: string, end?: string) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.analytics(systemEndpoints.analyticsAdminQuery.browserPath, {
      start,
      end,
    }).browserPath
  );
export const fetchAdminUserAnalytics = <T>(start?: string, end?: string) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.analytics(systemEndpoints.analyticsAdminUser.browserPath, {
      start,
      end,
    }).browserPath
  );
export const fetchAdminAtlasBotAnalytics = <T>(start?: string, end?: string) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.analytics(
      systemEndpoints.analyticsAdminAtlasbot.browserPath,
      { start, end }
    ).browserPath
  );
export const fetchPersonaMessagesAnalytics = <T>(
  personaId: number,
  start?: string,
  end?: string
) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.analytics(
      systemEndpoints.analyticsAdminPersonaMessages.browserPath,
      {
        persona_id: String(personaId),
        start,
        end,
      }
    ).browserPath
  );
export const fetchPersonaUniqueUsersAnalytics = <T>(
  personaId: number,
  start?: string,
  end?: string
) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.analytics(
      systemEndpoints.analyticsAdminPersonaUniqueUsers.browserPath,
      {
        persona_id: String(personaId),
        start,
        end,
      }
    ).browserPath
  );
export const fetchQueryHistoryTasks = <T>() =>
  fetchSystemSWRJson<T>(systemEndpoints.queryHistoryList.browserPath);
export const fetchChatSessionSnapshot = <T>(sessionId: string) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.chatSessionHistory(sessionId).browserPath
  );
export const fetchUsageReports = <T>() =>
  fetchSystemSWRJson<T>(systemEndpoints.usageReport.browserPath);
export const fetchChatSessionHistoryPage = <T>(params: URLSearchParams) =>
  fetchSystemSWRJson<T>(
    systemEndpoints.chatSessionHistoryPage(params).browserPath
  );

// ============================================================================
// System operations
// ============================================================================

export function fetchCurrentSearchSettings<T>(): Promise<T> {
  return fetchSystemSWRJson<T>(
    systemEndpoints.searchSettingsCurrent.browserPath
  );
}

export function fetchSecondarySearchSettings<T>(): Promise<T> {
  return fetchSystemSWRJson<T>(
    systemEndpoints.searchSettingsSecondary.browserPath
  );
}

export function fetchKeycloakSettings<T>(): Promise<T> {
  return fetchKeycloakData<T>();
}

export function fetchAppHealth(): Promise<unknown> {
  return requestSystemJson<unknown>(systemEndpoints.health.browserPath);
}

// ============================================================================
// Performance operations (merged into system)
// ============================================================================

export async function fetchGlobalTokenRateLimits<T = unknown>(): Promise<T> {
  return fetchSystemSWRJson<T>(
    systemEndpoints.tokenRateLimitsGlobal.browserPath
  );
}

export async function fetchUserTokenRateLimits<T = unknown>(): Promise<T> {
  return fetchSystemSWRJson<T>(
    systemEndpoints.tokenRateLimitsUsers.browserPath
  );
}

export async function fetchGroupTokenRateLimits<T = unknown>(): Promise<T> {
  return fetchSystemSWRJson<T>(
    systemEndpoints.tokenRateLimitsGroups.browserPath
  );
}

export async function fetchGroupTokenRateLimitsById<T = unknown>(
  groupId: number
): Promise<T> {
  return fetchSystemSWRJson<T>(
    systemEndpoints.groupTokenRateLimits(groupId).browserPath
  );
}

import { TokenRateLimitArgs } from "@/lib/api/domains/system/token-rate-limit-types";

export const insertGlobalTokenRateLimit = async (
  tokenRateLimit: TokenRateLimitArgs
) => {
  return await apiRequest(
    systemEndpoints.insertGlobalTokenRateLimit.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(tokenRateLimit),
    }
  );
};

export const insertUserTokenRateLimit = async (
  tokenRateLimit: TokenRateLimitArgs
) => {
  return await apiRequest(
    systemEndpoints.insertUserTokenRateLimit.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(tokenRateLimit),
    }
  );
};

export const insertGroupTokenRateLimit = async (
  tokenRateLimit: TokenRateLimitArgs,
  group_id: number
) => {
  return await apiRequest(
    systemEndpoints.insertGroupTokenRateLimit(group_id).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(tokenRateLimit),
    }
  );
};

export const deleteTokenRateLimit = async (token_rate_limit_id: number) => {
  return await apiRequest(
    systemEndpoints.deleteTokenRateLimit(token_rate_limit_id).browserPath,
    {
      method: "DELETE",
    }
  );
};

export const updateTokenRateLimit = async (
  token_rate_limit_id: number,
  tokenRateLimit: TokenRateLimitArgs
) => {
  return await apiRequest(
    systemEndpoints.deleteTokenRateLimit(token_rate_limit_id).browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(tokenRateLimit),
    }
  );
};

export function fetchLogCategories(): Promise<Response> {
  return apiRequest(systemEndpoints.fetchLogCategories.browserPath);
}

export function downloadLogCategory(category: string): Promise<Response> {
  return apiRequest(systemEndpoints.downloadLogCategory(category).browserPath);
}

export function updateCustomAnalyticsScriptResponse(payload: {
  script: string;
  secret_key: string;
}): Promise<Response> {
  return apiRequest(systemEndpoints.updateCustomAnalyticsScript.browserPath, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function requestUsageReport(payload: {
  period_from: string | null;
  period_to: string | null;
}): Promise<Response> {
  return apiRequest(systemEndpoints.usageReport.browserPath, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function updateEnterpriseTheme(payload: {
  application_name: string | null;
  use_custom_logo: boolean;
  use_custom_logotype: boolean;
  logo_display_style: "logo_and_name" | "logo_only" | "name_only" | null;
  custom_nav_items: import("@/interfaces/settings").NavigationItem[];
  custom_lower_disclaimer_content: string | null;
  custom_header_content: string | null;
  two_lines_for_chat_header: boolean | null;
  custom_popup_header: string | null;
  custom_popup_content: string | null;
  enable_consent_screen: boolean | null;
  consent_screen_prompt: string | null;
  show_first_visit_notice: boolean | null;
  custom_greeting_message: string | null;
}): Promise<Response> {
  return apiRequest(systemEndpoints.updateEnterpriseTheme.browserPath, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function uploadEnterpriseLogo(body: FormData): Promise<Response> {
  return apiRequest(systemEndpoints.uploadEnterpriseLogo.browserPath, {
    method: "PUT",
    body: body,
  });
}

export function fetchAgentUsageStats(
  agentId: number,
  pathValue: string,
  pathValue2: string
): Promise<Response> {
  return apiRequest(
    systemEndpoints.fetchAgentUsageStats(agentId, pathValue, pathValue2)
      .browserPath
  );
}

export function startQueryHistoryCsvExport(
  dateRange: { from: Date; to: Date } | undefined
): Promise<Response> {
  return apiRequest(
    systemEndpoints.startQueryHistoryCsvExport(dateRange).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
}

export function checkQueryHistoryCsvExport(
  requestId: string
): Promise<Response> {
  return apiRequest(
    systemEndpoints.checkQueryHistoryCsvExport(requestId).browserPath,
    {
      method: "GET",
    }
  );
}

export function syncExternalIdentityProvider(): Promise<Response> {
  return requestKeycloakResponse(
    systemEndpoints.syncExternalIdentityProvider().browserPath,
    {
      method: "POST",
    }
  );
}

export function patchKeycloakConfiguration(
  payload: Record<string, unknown>
): Promise<Response> {
  return requestKeycloakResponse(
    systemEndpoints.patchKeycloakConfiguration().browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function patchKeycloakRealmSession(
  payload: Record<string, unknown>
): Promise<Response> {
  return requestKeycloakResponse(
    systemEndpoints.patchKeycloakRealmSession().browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

import type {
  AvailableMailConfig,
  MailConfig,
  MailConfigCreatePayload,
  MailConfigTestResult,
  MailConfigUpdatePayload,
  McpToolConfigs,
  PaginatedMailConfigsResponse,
  UserMailSettings,
  UserMailSettingsPayload,
} from "@/lib/api/domains/system/types";
import i18n from "@/i18n/config";

async function fetchMailJson<T>(path: string): Promise<T> {
  const response = await apiRequest(path, {
    headers: { "X-Language": i18n.language || "en" },
  });
  return parseResponseModel<T>(response);
}

async function mutateMailJson<T>(
  path: string,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  payload?: unknown
): Promise<T> {
  const response = await apiRequest(path, {
    method,
    headers: {
      "X-Language": i18n.language || "en",
      ...(payload ? { "Content-Type": "application/json" } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await parseResponseModel<T>(response);
  return method === "DELETE" ? (undefined as T) : data;
}

export function fetchMailConfigs(
  path: string
): Promise<PaginatedMailConfigsResponse | MailConfig[]> {
  return fetchMailJson(path);
}
export function createMailConfig(
  payload: MailConfigCreatePayload
): Promise<MailConfig> {
  return mutateMailJson(
    systemEndpoints.mailConfigs.browserPath,
    "POST",
    payload
  );
}
export function updateMailConfig(
  id: string,
  payload: MailConfigUpdatePayload
): Promise<MailConfig> {
  return mutateMailJson(
    systemEndpoints.mailConfig(id).browserPath,
    "PATCH",
    payload
  );
}
export function deleteMailConfig(id: string): Promise<void> {
  return mutateMailJson(systemEndpoints.mailConfig(id).browserPath, "DELETE");
}
export function testMailConfig(
  id: string,
  toEmail: string
): Promise<MailConfigTestResult> {
  return mutateMailJson(
    systemEndpoints.mailConfigTest(id).browserPath,
    "POST",
    { to_email: toEmail }
  );
}
export function fetchUserMailSettings(): Promise<UserMailSettings | null> {
  return fetchMailJson(systemEndpoints.userMailSettings.browserPath);
}
export function fetchAvailableMailConfigs(): Promise<AvailableMailConfig[]> {
  return fetchMailJson(systemEndpoints.availableMailConfigs.browserPath);
}
export function saveUserMailSettings(
  payload: UserMailSettingsPayload
): Promise<UserMailSettings> {
  return mutateMailJson(
    systemEndpoints.userMailSettings.browserPath,
    "PUT",
    payload
  );
}
export function deleteUserMailSettings(): Promise<void> {
  return mutateMailJson(systemEndpoints.userMailSettings.browserPath, "DELETE");
}
export function testUserMailSettings(
  mailConfigId: string,
  toEmail?: string
): Promise<MailConfigTestResult> {
  return mutateMailJson(
    systemEndpoints.userMailSettingsTest.browserPath,
    "POST",
    {
      mail_config_id: mailConfigId,
      ...(toEmail ? { to_email: toEmail } : {}),
    }
  );
}

export function buildMcpToolConfigs(
  selectedToolNames: string[],
  mailConfigId?: string | null
): McpToolConfigs {
  if (!selectedToolNames.includes("send_email")) return {};
  const id = mailConfigId?.trim();
  if (!id)
    throw new Error("Mail config is required when send_email is selected");
  return { send_email: { mail_config_id: id } };
}

export async function getBackendVersion(): Promise<string | null> {
  try {
    const response = await apiRequest(systemEndpoints.version.browserPath, {
      redirectOnAuthError: false,
    });
    if (!response.ok) return null;
    const data: { backend_version: string } = await response.json();
    return data.backend_version;
  } catch (error) {
    console.log(`Error fetching backend version info: ${error}`);
    return null;
  }
}

async function requestKeycloakResponse(
  path: string,
  options: ApiRequestOptions = {}
): Promise<Response> {
  return userServicePayloadResponse(await apiRequest(path, options));
}

async function fetchKeycloakData<T>(): Promise<T> {
  const response = await requestKeycloakResponse(
    systemEndpoints.keycloakSettings.browserPath,
    { headers: { "X-Language": i18n.language } }
  );
  if (!response.ok) {
    const error = await parseApiErrorResponse(response);
    throw new FetchError(error.userMessage, response.status, error.raw, error);
  }
  return response.json() as Promise<T>;
}
