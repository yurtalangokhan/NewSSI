"use client";
import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";

import useSWR from "swr";
import { useSWRConfig } from "swr";
import type { FederatedConnectorDetail } from "@/lib/types";
import { fetchFederatedConnectors } from "@/lib/api/domains/integrations/api";

import { useMemo } from "react";
import type { FederatedConnectorOAuthStatus } from "@/lib/api/domains/integrations/types";
import { fetchOAuthStatus } from "@/lib/api/domains/integrations/api";

export function useFederatedConnectors() {
  const { mutate } = useSWRConfig();
  const swrResponse = useSWR<FederatedConnectorDetail[]>(
    integrationsEndpoints.federatedConnectors.browserPath,
    () => fetchFederatedConnectors<FederatedConnectorDetail[]>()
  );
  return {
    ...swrResponse,
    refreshFederatedConnectors: () =>
      mutate(integrationsEndpoints.federatedConnectors.browserPath),
  };
}

/**
 * Hook for fetching federated OAuth connector authentication status.
 *
 * Retrieves the authentication status for all federated connectors (e.g., Gmail,
 * Google Drive, Slack) and provides utilities to identify which connectors need
 * OAuth authentication. Uses SWR for caching and automatic revalidation.
 *
 * @returns Object containing:
 *   - connectors: Array of all federated connector statuses
 *   - needsAuth: Array of connectors that lack OAuth tokens
 *   - hasUnauthenticatedConnectors: Boolean indicating if any connectors need auth
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Error object if the fetch failed
 *   - refetch: Function to manually reload connector statuses
 *
 * @example
 * ```tsx
 * // Display connectors requiring authentication
 * const OAuthPrompt = () => {
 *   const { needsAuth, isLoading } = useFederatedOAuthStatus();
 *
 *   if (isLoading) return <Spinner />;
 *   if (needsAuth.length === 0) return null;
 *
 *   return (
 *     <div>
 *       <h3>Connect your accounts:</h3>
 *       {needsAuth.map(connector => (
 *         <ConnectButton key={connector.source} connector={connector} />
 *       ))}
 *     </div>
 *   );
 * };
 * ```
 *
 * @example
 * ```tsx
 * // Show warning banner if any connectors need authentication
 * const AuthWarningBanner = () => {
 *   const { hasUnauthenticatedConnectors } = useFederatedOAuthStatus();
 *
 *   if (!hasUnauthenticatedConnectors) return null;
 *
 *   return (
 *     <Banner variant="warning">
 *       Some connectors need authentication to access your data.
 *     </Banner>
 *   );
 * };
 * ```
 *
 * @example
 * ```tsx
 * // List all connectors with their auth status
 * const ConnectorList = () => {
 *   const { connectors, refetch } = useFederatedOAuthStatus();
 *
 *   return (
 *     <div>
 *       {connectors.map(connector => (
 *         <ConnectorRow
 *           key={connector.source}
 *           connector={connector}
 *           authenticated={connector.has_oauth_token}
 *           onReconnect={refetch}
 *         />
 *       ))}
 *     </div>
 *   );
 * };
 * ```
 */
export function useFederatedOAuthStatus() {
  const { data, error, isLoading, mutate } = useSWR<
    FederatedConnectorOAuthStatus[]
  >(integrationsEndpoints.oauthStatus.browserPath, () =>
    fetchOAuthStatus<FederatedConnectorOAuthStatus[]>()
  );

  const connectors = data ?? [];
  const needsAuth = useMemo(
    () => (data ?? []).filter((c) => !c.has_oauth_token),
    [data]
  );
  const hasUnauthenticatedConnectors = needsAuth.length > 0;

  return {
    connectors,
    needsAuth,
    hasUnauthenticatedConnectors,
    isLoading,
    error,
    refetch: mutate,
  };
}
