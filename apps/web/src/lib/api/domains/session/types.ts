import type { AuthType } from "@/lib/constants";

export interface AuthTypeMetadata {
  authType: AuthType;
  autoRedirect: boolean;
  requiresVerification: boolean;
  anonymousUserEnabled: boolean | null;
  hasUsers: boolean;
  oauthEnabled: boolean;
  keycloakEnabled?: boolean;
  externalKeycloak: boolean;
  external_keycloak?: boolean;
  externalKeycloakAlias?: string | null;
}

export interface PersonalAccessToken {
  id: number;
  name: string;
  token_display: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}
