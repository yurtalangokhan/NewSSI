export type ToolUpdatePayload = {
  name?: string;
  description?: string;
  definition?: Record<string, unknown>;
  custom_headers?: { key: string; value: string }[] | null;
  passthrough_auth?: boolean;
  oauth_config_id?: number | null;
};
