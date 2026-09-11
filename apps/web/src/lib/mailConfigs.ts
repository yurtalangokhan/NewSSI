import useSWR from "swr";
import { authenticatedFetch } from "@/lib/fetcher";
import i18n from "@/i18n/config";

export type MailSecurity = "ssl" | "starttls" | "none";

export interface MailConfig {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string | null;
  from_email: string | null;
  from_name: string | null;
  security: MailSecurity;
  is_active: boolean;
  password_configured: boolean;
  last_tested_at: string | null;
  last_test_status?: "success" | "failed" | null;
  last_test_error?: string | null;
  time_created: string | null;
  time_updated: string | null;
}

export interface PaginatedMailConfigsResponse {
  items: MailConfig[];
  total_items: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface UseMailConfigsOptions {
  search?: string;
  page?: number;
  pageSize?: number;
}

export interface MailConfigCreatePayload {
  name: string;
  host: string;
  port: number;
  security: MailSecurity;
  username?: string | null;
  password?: string | null;
  from_email?: string | null;
  from_name?: string | null;
}

export interface MailConfigUpdatePayload {
  name?: string;
  host?: string;
  port?: number;
  security?: MailSecurity;
  username?: string | null;
  password?: string | null;
  from_email?: string | null;
  from_name?: string | null;
  is_active?: boolean;
}

export interface MailConfigTestResult {
  success: boolean;
  message: string;
}

export interface UserMailSettings {
  mail_config_id: string;
  username: string;
  from_email: string;
  from_name: string | null;
  password_configured: boolean;
  is_active: boolean;
  last_tested_at: string | null;
  time_created: string | null;
  time_updated: string | null;
}

export interface UserMailSettingsPayload {
  mail_config_id: string;
  username: string;
  password?: string;
  from_email: string;
  from_name?: string | null;
}

export interface AvailableMailConfig {
  id: string;
  name: string;
  host: string;
  port: number;
  security: MailSecurity;
}

export type McpToolConfigs = {
  send_email?: {
    mail_config_id: string;
  };
};

const MAIL_CONFIGS_ENDPOINT = "/api/mail-configs";

async function fetcher<T>(url: string): Promise<T> {
  const response = await authenticatedFetch(url, {
    headers: { "X-Language": i18n.language || "en" },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function requestJson<T>(
  url: string,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  payload?: unknown
): Promise<T> {
  const response = await authenticatedFetch(url, {
    method,
    headers: {
      "X-Language": i18n.language || "en",
      ...(payload ? { "Content-Type": "application/json" } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  if (method === "DELETE") {
    return undefined as T;
  }
  return response.json();
}

export function useMailConfigs(options?: UseMailConfigsOptions) {
  const { search, page, pageSize } = options || {};

  const queryParams = new URLSearchParams();
  if (search && search.trim()) {
    queryParams.set("search", search.trim());
  }
  if (page !== undefined) {
    queryParams.set("page", String(page));
  }
  if (pageSize !== undefined) {
    queryParams.set("page_size", String(pageSize));
  }

  const queryString = queryParams.toString();
  const url = queryString
    ? `${MAIL_CONFIGS_ENDPOINT}?${queryString}`
    : MAIL_CONFIGS_ENDPOINT;

  const { data, error, isLoading, mutate } = useSWR<
    PaginatedMailConfigsResponse | MailConfig[]
  >(url, fetcher);

  const mailConfigs: MailConfig[] = Array.isArray(data)
    ? data
    : data?.items || [];
  const totalItems: number = Array.isArray(data)
    ? data.length
    : data?.total_items || 0;
  const totalPages: number = Array.isArray(data)
    ? Math.max(1, Math.ceil(data.length / (pageSize || 10)))
    : data?.total_pages || 1;
  const currentPage: number = Array.isArray(data)
    ? page || 1
    : data?.page || page || 1;

  return {
    mailConfigs,
    totalItems,
    totalPages,
    currentPage,
    error,
    isLoading,
    refreshMailConfigs: mutate,
  };
}

export function createMailConfig(payload: MailConfigCreatePayload) {
  return requestJson<MailConfig>(MAIL_CONFIGS_ENDPOINT, "POST", payload);
}

export function updateMailConfig(id: string, payload: MailConfigUpdatePayload) {
  return requestJson<MailConfig>(
    `${MAIL_CONFIGS_ENDPOINT}/${id}`,
    "PATCH",
    payload
  );
}

export function deleteMailConfig(id: string) {
  return requestJson<void>(`${MAIL_CONFIGS_ENDPOINT}/${id}`, "DELETE");
}

export function testMailConfig(id: string, toEmail: string) {
  return requestJson<MailConfigTestResult>(
    `${MAIL_CONFIGS_ENDPOINT}/${id}/test`,
    "POST",
    { to_email: toEmail }
  );
}

export function useUserMailSettings() {
  const { data, error, isLoading, mutate } = useSWR<UserMailSettings | null>(
    `${MAIL_CONFIGS_ENDPOINT}/user-credentials`,
    fetcher
  );

  return {
    userMailSettings: data ?? null,
    error,
    isLoading,
    refreshUserMailSettings: mutate,
  };
}

export function useAvailableMailConfigs() {
  const { data, error, isLoading } = useSWR<AvailableMailConfig[]>(
    `${MAIL_CONFIGS_ENDPOINT}/available`,
    fetcher
  );

  return {
    availableMailConfigs: data ?? [],
    error,
    isLoading,
  };
}

export function saveUserMailSettings(payload: UserMailSettingsPayload) {
  return requestJson<UserMailSettings>(
    `${MAIL_CONFIGS_ENDPOINT}/user-credentials`,
    "PUT",
    payload
  );
}

export function deleteUserMailSettings() {
  return requestJson<void>(
    `${MAIL_CONFIGS_ENDPOINT}/user-credentials`,
    "DELETE"
  );
}

export function testUserMailSettings(mailConfigId: string, toEmail?: string) {
  return requestJson<MailConfigTestResult>(
    `${MAIL_CONFIGS_ENDPOINT}/user-credentials/test`,
    "POST",
    { mail_config_id: mailConfigId, ...(toEmail ? { to_email: toEmail } : {}) }
  );
}

export function buildMcpToolConfigs(
  selectedToolNames: string[],
  mailConfigId?: string | null
): McpToolConfigs {
  if (!selectedToolNames.includes("send_email")) {
    return {};
  }

  const trimmedMailConfigId = mailConfigId?.trim();
  if (!trimmedMailConfigId) {
    throw new Error("Mail config is required when send_email is selected");
  }

  return {
    send_email: {
      mail_config_id: trimmedMailConfigId,
    },
  };
}
