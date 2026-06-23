// Discord bot service API key name - should match backend constant
export const DISCORD_SERVICE_API_KEY_NAME = "discord-bot-service";

// API key role values (separate from user roles)
export type ApiKeyRole = "admin" | "enduser";

export interface APIKey {
  api_key_id: number;
  api_key_display: string;
  api_key: string | null;
  api_key_name: string | null;
  api_key_role: ApiKeyRole;
  user_id: string;
}

export interface APIKeyArgs {
  name?: string;
  role: ApiKeyRole;
}
