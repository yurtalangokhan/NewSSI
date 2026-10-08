// System Domain API types
// Merged from performance module

export interface QueryHistoryEntry {
  id: string;
  query: string;
  response_time_ms: number;
  timestamp: string;
  user_id?: string;
}

export interface QueryHistoryListResponse {
  entries: QueryHistoryEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface ExportStatus {
  status: "pending" | "processing" | "completed" | "failed";
  progress?: number;
  download_url?: string;
}

export interface UsageReport {
  period: string;
  total_queries: number;
  total_users: number;
  average_response_time_ms: number;
}

export interface ChatSessionHistory {
  session_id: string;
  messages: Array<{
    role: string;
    content: string;
    timestamp: string;
  }>;
}

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
export type McpToolConfigs = { send_email?: { mail_config_id: string } };
