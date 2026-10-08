import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";

import type {
  OAuthBaseCallbackResponse,
  OAuthConfluenceFinalizeResponse,
  OAuthConfluencePrepareFinalizationResponse,
  OAuthPrepareAuthorizationResponse,
  OAuthSlackCallbackResponse,
  SlackBot,
} from "@/lib/types";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

export async function fetchConnectorOAuthDetails<T>(
  source: string
): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.connectorOAuthDetails(source).browserPath
  );
}

async function fetchIntegrationSWRJson<T>(path: string): Promise<T> {
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

export async function fetchFederatedConnectors<T>(): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.federatedConnectors.browserPath
  );
}

export function fetchOAuthStatus<T = unknown>() {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.oauthStatus.browserPath
  );
}

export function handleOAuthAuthorizationResponse(
  connector: string,
  code: string,
  state: string
) {
  if (connector === "slack") {
    return handleOAuthSlackAuthorizationResponse(code, state);
  }
  if (connector === "google-drive") {
    return handleOAuthGoogleDriveAuthorizationResponse(code, state);
  }
  if (connector === "confluence") {
    return handleOAuthConfluenceAuthorizationResponse(code, state);
  }
  return undefined;
}

// Additional endpoints for Slack, Google, mail, and connector callbacks

export async function updateSlackBotField(
  slackBot: SlackBot,
  field: keyof SlackBot,
  value: unknown
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.slackBotDetail(slackBot.id).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...slackBot, [field]: value }),
    }
  );
}

// Slack endpoints

export async function fetchSlackChannelConfigs<T>(): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.slackChannelConfig.browserPath
  );
}

export async function fetchSlackBots<T>(): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.slackBots.browserPath
  );
}

export async function fetchSlackBot<T>(botId: number): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.fetchSlackBot(encodeURIComponent(botId)).browserPath
  );
}

export async function fetchSlackChannelConfigsByBot<T>(
  botId: number
): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.slackChannelConfigByBot(botId).browserPath
  );
}

// Discord endpoints

export async function fetchDiscordGuilds<T>(): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.discordGuildCatalog.browserPath
  );
}

export async function fetchDiscordGuild<T>(configId: number): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.discordGuild(configId).browserPath
  );
}

export async function fetchDiscordChannels<T>(
  guildConfigId: number
): Promise<T> {
  return fetchIntegrationSWRJson<T>(
    integrationsEndpoints.discordChannels(guildConfigId).browserPath
  );
}

// Gmail connector endpoints

export async function setupGmailOAuth({
  isAdmin,
}: {
  isAdmin: boolean;
}): Promise<[string | null, string]> {
  const credentialCreationResponse = await apiRequest(
    integrationsEndpoints.gmailCredential.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        admin_public: isAdmin,
        credential_json: {},
        source: "gmail",
      }),
    }
  );

  if (!credentialCreationResponse.ok) {
    return [
      null,
      `Failed to create credential - ${credentialCreationResponse.status}`,
    ];
  }
  const credential = (await credentialCreationResponse.json()) as {
    id: number;
  };

  const authorizationUrlResponse = await apiRequest(
    integrationsEndpoints.gmailAuthorize(credential.id).browserPath
  );
  if (!authorizationUrlResponse.ok) {
    return [
      null,
      `Failed to create credential - ${authorizationUrlResponse.status}`,
    ];
  }
  const authorizationUrlJson = (await authorizationUrlResponse.json()) as {
    auth_url: string;
  };

  return [authorizationUrlJson.auth_url, ""];
}

// Google Drive connector endpoints

export async function setupGoogleDriveOAuth({
  isAdmin,
  name,
}: {
  isAdmin: boolean;
  name: string;
}): Promise<[string | null, string]> {
  const credentialCreationResponse = await apiRequest(
    integrationsEndpoints.googleDriveCredential.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        admin_public: isAdmin,
        credential_json: {},
        source: "google_drive",
        name: name,
      }),
    }
  );

  if (!credentialCreationResponse.ok) {
    return [
      null,
      `Failed to create credential - ${credentialCreationResponse.status}`,
    ];
  }
  const credential = (await credentialCreationResponse.json()) as {
    id: number;
  };

  const authorizationUrlResponse = await apiRequest(
    integrationsEndpoints.googleDriveAuthorize(credential.id).browserPath
  );
  if (!authorizationUrlResponse.ok) {
    return [
      null,
      `Failed to create credential - ${authorizationUrlResponse.status}`,
    ];
  }

  const authorizationUrlJson = (await authorizationUrlResponse.json()) as {
    auth_url: string;
  };

  return [authorizationUrlJson.auth_url, ""];
}

// Migrated OAuth actions (behavior-preserving)
export async function prepareOAuthAuthorizationRequest(
  connector: string,
  finalRedirect: string | null // a redirect (not the oauth redirect) for the user to return to after oauth is complete)
): Promise<OAuthPrepareAuthorizationResponse> {
  let url = integrationsEndpoints.prepareOAuthAuthorizationRequest(
    encodeURIComponent(connector)
  ).browserPath;

  // Conditionally append the `redirect_on_success` parameter
  if (finalRedirect) {
    url += `&redirect_on_success=${encodeURIComponent(finalRedirect)}`;
  }

  const response = await apiRequest(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      connector: connector,
      redirect_on_success: finalRedirect,
    }),
  });

  if (!response.ok) {
    throw new Error(
      `Failed to prepare OAuth authorization request: ${response.status}`
    );
  }

  // Parse the JSON response
  const data = (await response.json()) as OAuthPrepareAuthorizationResponse;
  return data;
}

export async function handleOAuthSlackAuthorizationResponse(
  code: string,
  state: string
): Promise<OAuthSlackCallbackResponse> {
  const url = integrationsEndpoints.handleOAuthSlackAuthorization(
    encodeURIComponent(code),
    encodeURIComponent(state)
  ).browserPath;

  const response = await apiRequest(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, state }),
  });

  if (!response.ok) {
    let errorDetails = `Failed to handle OAuth Slack authorization response: ${response.status}`;

    try {
      const responseBody = await response.text(); // Read the body as text
      errorDetails += `\nResponse Body: ${responseBody}`;
    } catch (err) {
      if (err instanceof Error) {
        errorDetails += `\nUnable to read response body: ${err.message}`;
      } else {
        errorDetails += `\nUnable to read response body: Unknown error type`;
      }
    }

    throw new Error(errorDetails);
  }

  // Parse the JSON response
  const data = (await response.json()) as OAuthSlackCallbackResponse;
  return data;
}

export async function handleOAuthGoogleDriveAuthorizationResponse(
  code: string,
  state: string
): Promise<OAuthBaseCallbackResponse> {
  const url = integrationsEndpoints.handleOAuthGoogleDriveAuthorization(
    encodeURIComponent(code),
    encodeURIComponent(state)
  ).browserPath;

  const response = await apiRequest(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, state }),
  });

  if (!response.ok) {
    let errorDetails = `Failed to handle OAuth Google Drive authorization response: ${response.status}`;

    try {
      const responseBody = await response.text(); // Read the body as text
      errorDetails += `\nResponse Body: ${responseBody}`;
    } catch (err) {
      if (err instanceof Error) {
        errorDetails += `\nUnable to read response body: ${err.message}`;
      } else {
        errorDetails += `\nUnable to read response body: Unknown error type`;
      }
    }

    throw new Error(errorDetails);
  }

  // Parse the JSON response
  const data = (await response.json()) as OAuthBaseCallbackResponse;
  return data;
}

export async function handleOAuthConfluenceAuthorizationResponse(
  code: string,
  state: string
): Promise<OAuthBaseCallbackResponse> {
  const url = integrationsEndpoints.handleOAuthConfluenceAuthorization(
    encodeURIComponent(code),
    encodeURIComponent(state)
  ).browserPath;

  const response = await apiRequest(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, state }),
  });

  if (!response.ok) {
    let errorDetails = `Failed to handle OAuth Confluence authorization response: ${response.status}`;

    try {
      const responseBody = await response.text(); // Read the body as text
      errorDetails += `\nResponse Body: ${responseBody}`;
    } catch (err) {
      if (err instanceof Error) {
        errorDetails += `\nUnable to read response body: ${err.message}`;
      } else {
        errorDetails += `\nUnable to read response body: Unknown error type`;
      }
    }

    throw new Error(errorDetails);
  }

  // Parse the JSON response
  const data = (await response.json()) as OAuthBaseCallbackResponse;
  return data;
}

export async function handleOAuthPrepareFinalization(
  connector: string,
  credential: number
) {
  if (connector === "confluence") {
    return handleOAuthConfluencePrepareFinalization(credential);
  }

  return;
}

export async function handleOAuthConfluencePrepareFinalization(
  credential: number
): Promise<OAuthConfluencePrepareFinalizationResponse> {
  const url = integrationsEndpoints.handleOAuthConfluencePrepareFinalization(
    encodeURIComponent(credential)
  ).browserPath;

  const response = await apiRequest(url, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    let errorDetails = `Failed to handle OAuth Confluence prepare finalization response: ${response.status}`;

    try {
      const responseBody = await response.text(); // Read the body as text
      errorDetails += `\nResponse Body: ${responseBody}`;
    } catch (err) {
      if (err instanceof Error) {
        errorDetails += `\nUnable to read response body: ${err.message}`;
      } else {
        errorDetails += `\nUnable to read response body: Unknown error type`;
      }
    }

    throw new Error(errorDetails);
  }

  // Parse the JSON response
  const data =
    (await response.json()) as OAuthConfluencePrepareFinalizationResponse;
  return data;
}

export async function handleOAuthConfluenceFinalize(
  credential_id: number,
  cloud_id: string,
  cloud_name: string,
  cloud_url: string
): Promise<OAuthConfluenceFinalizeResponse> {
  const url = integrationsEndpoints.handleOAuthConfluenceFinalize(
    encodeURIComponent(credential_id),
    encodeURIComponent(cloud_id),
    encodeURIComponent(cloud_name),
    encodeURIComponent(cloud_url)
  ).browserPath;

  const response = await apiRequest(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    let errorDetails = `Failed to handle OAuth Confluence finalization response: ${response.status}`;

    try {
      const responseBody = await response.text(); // Read the body as text
      errorDetails += `\nResponse Body: ${responseBody}`;
    } catch (err) {
      if (err instanceof Error) {
        errorDetails += `\nUnable to read response body: ${err.message}`;
      } else {
        errorDetails += `\nUnable to read response body: Unknown error type`;
      }
    }

    throw new Error(errorDetails);
  }

  // Parse the JSON response
  const data = (await response.json()) as OAuthConfluenceFinalizeResponse;
  return data;
}

import {
  SlackChannelConfigCreationRequest,
  buildRequestBodyFromCreationRequest,
} from "@/lib/api/domains/integrations/slack-channel-requests";

export const createSlackChannelConfig = async (
  creationRequest: SlackChannelConfigCreationRequest
) => {
  return apiRequest(integrationsEndpoints.createSlackChannel.browserPath, {
    method: integrationsEndpoints.createSlackChannel.method,
    headers: {
      "Content-Type": "application/json",
    },
    body: buildRequestBodyFromCreationRequest(creationRequest),
  });
};

export const updateSlackChannelConfig = async (
  id: number,
  creationRequest: SlackChannelConfigCreationRequest
) => {
  return apiRequest(
    integrationsEndpoints.updateSlackChannelConfig(id).browserPath,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: buildRequestBodyFromCreationRequest(creationRequest),
    }
  );
};

export const deleteSlackChannelConfig = async (id: number) => {
  return apiRequest(
    integrationsEndpoints.updateSlackChannelConfig(id).browserPath,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
};

import {
  DiscordBotConfig,
  DiscordGuildConfig,
  DiscordGuildConfigCreateResponse,
  DiscordGuildConfigUpdate,
  DiscordChannelConfig,
  DiscordChannelConfigUpdate,
} from "@/lib/api/domains/integrations/discord-types";

export async function createBotConfig(
  botToken: string
): Promise<DiscordBotConfig> {
  const response = await apiRequest(
    integrationsEndpoints.fetchBotConfig.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bot_token: botToken }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to create bot config");
  }
  return response.json();
}

export async function deleteBotConfig(): Promise<void> {
  const response = await apiRequest(
    integrationsEndpoints.fetchBotConfig.browserPath,
    {
      method: "DELETE",
    }
  );
  if (!response.ok) {
    throw new Error("Failed to delete bot config");
  }
}

export async function createGuildConfig(): Promise<DiscordGuildConfigCreateResponse> {
  const response = await apiRequest(
    integrationsEndpoints.fetchGuildConfigs.browserPath,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to create guild config");
  }
  return response.json();
}

export async function updateGuildConfig(
  configId: number,
  update: DiscordGuildConfigUpdate
): Promise<DiscordGuildConfig> {
  const response = await apiRequest(
    integrationsEndpoints.fetchGuildConfig(configId).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to update guild config");
  }
  return response.json();
}

export async function deleteGuildConfig(configId: number): Promise<void> {
  const response = await apiRequest(
    integrationsEndpoints.fetchGuildConfig(configId).browserPath,
    {
      method: "DELETE",
    }
  );
  if (!response.ok) {
    throw new Error("Failed to delete guild config");
  }
}

export async function updateChannelConfig(
  guildConfigId: number,
  channelConfigId: number,
  update: DiscordChannelConfigUpdate
): Promise<DiscordChannelConfig> {
  const response = await apiRequest(
    integrationsEndpoints.updateChannelConfig(guildConfigId, channelConfigId)
      .browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to update channel config");
  }
  return response.json();
}

export async function bulkUpdateChannelConfigs(
  guildConfigId: number,
  updates: { channelConfigId: number; update: DiscordChannelConfigUpdate }[]
): Promise<{ succeeded: number; failed: number }> {
  let succeeded = 0;
  let failed = 0;

  for (const { channelConfigId, update } of updates) {
    try {
      await updateChannelConfig(guildConfigId, channelConfigId, update);
      succeeded++;
    } catch {
      failed++;
    }
  }

  return { succeeded, failed };
}

import {
  OAuthConfig,
  OAuthConfigCreate,
  OAuthConfigUpdate,
  OAuthTokenStatus,
} from "@/lib/tools/interfaces";
import { parseApiErrorPayload } from "@/lib/api/errors";

export async function createOAuthConfig(
  config: OAuthConfigCreate
): Promise<OAuthConfig> {
  const response = await apiRequest(
    integrationsEndpoints.oauthConfigCreate.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );

  if (!response.ok) {
    const parsed = parseApiErrorPayload(
      await response.json().catch(() => null),
      response.status
    );
    throw new Error(
      parsed.userMessage ||
        `Failed to create OAuth config: ${response.statusText}`
    );
  }

  return await response.json();
}

export async function getOAuthConfig(id: number): Promise<OAuthConfig> {
  const response = await apiRequest(
    integrationsEndpoints.oAuthConfig(id).browserPath
  );

  if (!response.ok) {
    const parsed = parseApiErrorPayload(
      await response.json().catch(() => null),
      response.status
    );
    throw new Error(
      parsed.userMessage ||
        `Failed to fetch OAuth config: ${response.statusText}`
    );
  }

  return await response.json();
}

export async function updateOAuthConfig(
  id: number,
  updates: OAuthConfigUpdate
): Promise<OAuthConfig> {
  const response = await apiRequest(
    integrationsEndpoints.oAuthConfig(id).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }
  );

  if (!response.ok) {
    const parsed = parseApiErrorPayload(
      await response.json().catch(() => null),
      response.status
    );
    throw new Error(
      parsed.userMessage ||
        `Failed to update OAuth config: ${response.statusText}`
    );
  }

  return await response.json();
}

export async function initiateOAuthFlow(
  oauthConfigId: number,
  returnPath: string = "/app"
): Promise<void> {
  const response = await apiRequest(
    integrationsEndpoints.oauthInitiate.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        oauth_config_id: oauthConfigId,
        return_path: returnPath,
      }),
    }
  );

  if (!response.ok) {
    const parsed = parseApiErrorPayload(
      await response.json().catch(() => null),
      response.status
    );
    throw new Error(
      parsed.userMessage ||
        `Failed to initiate OAuth flow: ${response.statusText}`
    );
  }

  const data = await response.json();
  // Redirect to authorization URL
  window.location.href = data.authorization_url;
}

function completeOAuthCallback(path: string): Promise<Response> {
  return apiRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
}

export function completeFederatedOAuthCallback(
  code: string,
  state: string
): Promise<Response> {
  return completeOAuthCallback(
    integrationsEndpoints.completeFederatedCallback(code, state).browserPath
  );
}

export function completeOAuthConfigCallback(
  code: string,
  state: string
): Promise<Response> {
  return completeOAuthCallback(
    integrationsEndpoints.oauthConfigCallback(code, state).browserPath
  );
}

export async function getUserOAuthTokenStatus(): Promise<OAuthTokenStatus[]> {
  const response = await apiRequest(
    integrationsEndpoints.userOauthTokenStatus.browserPath
  );

  // Local/dev backends may not implement OAuth token APIs yet.
  // Treat this as "no user OAuth tokens" instead of a hard UI failure.
  if (response.status === 404 || response.status === 501) {
    return [];
  }

  if (!response.ok) {
    const parsed = parseApiErrorPayload(
      await response.json().catch(() => null),
      response.status
    );
    throw new Error(
      parsed.userMessage ||
        `Failed to fetch OAuth token status: ${
          response.statusText || response.status
        }`
    );
  }

  return await response.json();
}

export function fetchFederatedConnectorDetail(
  connectorId: string
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.fetchFederatedConnectorDetail(connectorId).browserPath
  );
}

export function fetchFederatedCredentialSchema(
  extractedSourceType: import("@/lib/types").ConfigurableSources
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.fetchFederatedCredentialSchema(extractedSourceType)
      .browserPath
  );
}

export function validateFederatedCredentials(
  source: string,
  payload: Record<string, string>
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.validateFederatedCredentials(source).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function createFederatedConnection(
  payload: import("@/lib/types").FederatedConnectorCreateRequest
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.createFederatedConnection.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function updateFederatedConnection(
  id: number,
  payload: {
    credentials: Record<string, string>;
    config: Record<string, string | boolean | string[] | number | undefined>;
  }
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.updateFederatedConnection(id).browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function deleteFederatedConnection(id: number): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.updateFederatedConnection(id).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function loadFederatedConfigurationSchema(
  connector: import("@/lib/types").ConfigurableSources
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.loadFederatedConfigurationSchema(connector)
      .browserPath
  );
}

import {
  SlackBotCreationRequest,
  buildRequestBodyFromCreationRequest as buildSlackBotRequestBody,
} from "@/lib/api/domains/integrations/slack-bot-requests";
import i18n from "@/i18n/config";

export const createSlackBot = async (
  creationRequest: SlackBotCreationRequest
) => {
  return apiRequest(integrationsEndpoints.createSlackBot.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: buildSlackBotRequestBody(creationRequest),
  });
};

export const updateSlackBot = async (
  id: number,
  creationRequest: SlackBotCreationRequest
) => {
  return apiRequest(integrationsEndpoints.updateSlackBot(id).browserPath, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: buildSlackBotRequestBody(creationRequest),
  });
};

export const deleteSlackBot = async (id: number) => {
  return apiRequest(integrationsEndpoints.updateSlackBot(id).browserPath, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
  });
};

export function fetchDiscordManagedConfig(): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.fetchDiscordManagedConfig.browserPath
  );
}

export function disconnectFederatedOAuthResponse(
  federated_connector_id: number
): Promise<Response> {
  return apiRequest(
    integrationsEndpoints.disconnectFederatedOAuth(federated_connector_id)
      .browserPath,
    { method: "DELETE" }
  );
}
