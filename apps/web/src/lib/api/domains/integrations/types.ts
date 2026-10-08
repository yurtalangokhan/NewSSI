export interface FederatedConnectorOAuthStatus {
  federated_connector_id: number;
  source: string;
  name: string;
  has_oauth_token: boolean;
  oauth_token_expires_at?: string;
  authorize_url?: string;
}
