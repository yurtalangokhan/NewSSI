import useSWR from "swr";
import { authenticatedFetch } from "@/lib/fetcher";
import i18n from "@/i18n/config";

export type MailSecurity = "ssl" | "starttls" | "none";

export interface MailConfig {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string | null;
  security: MailSecurity;
  is_active: boolean;
  password_configured: boolean;
  last_tested_at: string | null;
  time_created: string | null;
  time_updated: string | null;
}

export interface MailConfigCreatePayload {
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  from_email: string;
  from_name?: string | null;
  security: MailSecurity;
}

export interface MailConfigUpdatePayload {
  name?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  from_email?: string;
  from_name?: string | null;
  security?: MailSecurity;
  is_active?: boolean;
}

export interface MailConfigTestResult {
  success: boolean;
  message: string;
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
  method: "POST" | "PATCH" | "DELETE",
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

export function useMailConfigs() {
  const { data, error, isLoading, mutate } = useSWR<MailConfig[]>(
    MAIL_CONFIGS_ENDPOINT,
    fetcher
  );

  return {
    mailConfigs: data ?? [],
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
