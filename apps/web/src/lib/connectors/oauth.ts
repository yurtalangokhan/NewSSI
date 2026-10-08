import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";

import { fetchConnectorOAuthRedirectResponse } from "@/lib/api/domains/datasources/api";
import { fetchConnectorOAuthDetails } from "@/lib/api/domains/integrations/api";

import useSWR from "swr";
import { ValidSources } from "../types";
import { OAuthDetails } from "./credentials";

export async function getConnectorOauthRedirectUrl(
  connector: ValidSources,
  additional_kwargs: Record<string, string>
): Promise<string | null> {
  const queryParams = new URLSearchParams({
    desired_return_url: window.location.href,
    ...additional_kwargs,
  });
  const response = await fetchConnectorOAuthRedirectResponse(
    connector,
    queryParams
  );

  if (!response.ok) {
    console.error(`Failed to fetch OAuth redirect URL for ${connector}`);
    return null;
  }

  const data = await response.json();
  return data.redirect_url as string;
}

export function useOAuthDetails(sourceType: ValidSources) {
  return useSWR<OAuthDetails>(
    integrationsEndpoints.connectorOAuthDetails(sourceType).browserPath,
    () => fetchConnectorOAuthDetails<OAuthDetails>(sourceType),
    {
      shouldRetryOnError: false,
    }
  );
}
