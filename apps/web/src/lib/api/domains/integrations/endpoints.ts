export const integrationsEndpoints = {
  listSlackChannels: {
    method: "GET",
    browserPath: "/api/manage/admin/slack-app/channel",
    backend: {
      service: "agent",
      path: "/api/v1/manage/admin/slack-app/channel",
    },
  },
  createSlackChannel: {
    method: "POST",
    browserPath: "/api/manage/admin/slack-app/channel",
    backend: {
      service: "agent",
      path: "/api/v1/manage/admin/slack-app/channel",
    },
  },
  oauthStatus: { browserPath: "/api/federated/oauth-status" },
  federatedCallback: { browserPath: "/api/federated/callback" },
  completeFederatedCallback: (
    code: string,
    state: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        integrationsEndpoints.federatedCallback.browserPath
      }?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
    };
  },
  updateSlackChannelConfig: (id: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/slack-app/channel/${id}` };
  },
  base: { browserPath: "/api/manage/admin/discord-bot" },
  fetchBotConfig: { browserPath: "/api/manage/admin/discord-bot/config" },
  fetchGuildConfigs: { browserPath: "/api/manage/admin/discord-bot/guilds" },
  fetchGuildConfig: (configId: number): { browserPath: string } => {
    return {
      browserPath: `${integrationsEndpoints.base.browserPath}/guilds/${configId}`,
    };
  },
  updateChannelConfig: (
    guildConfigId: number,
    channelConfigId: number
  ): { browserPath: string } => {
    return {
      browserPath: `${integrationsEndpoints.base.browserPath}/guilds/${guildConfigId}/channels/${channelConfigId}`,
    };
  },
  oauthConfigCreate: { browserPath: "/api/admin/oauth-config/create" },
  oauthConfigs: { browserPath: "/api/admin/oauth-config" },
  oAuthConfig: (id: number): { browserPath: string } => ({
    browserPath: `${
      integrationsEndpoints.oauthConfigs.browserPath
    }/${encodeURIComponent(id)}`,
  }),
  oauthInitiate: { browserPath: "/api/oauth-config/initiate" },
  oauthCallback: { browserPath: "/api/oauth-config/callback" },
  oauthConfigCallback: (
    code: string,
    state: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        integrationsEndpoints.oauthCallback.browserPath
      }?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
    };
  },
  userOauthTokenStatus: { browserPath: "/api/user-oauth-token/status" },
  fetchFederatedConnectorDetail: (
    connectorId: string
  ): { browserPath: string } => {
    return { browserPath: `/api/federated/${connectorId}` };
  },
  fetchFederatedCredentialSchema: (
    extractedSourceType: import("@/lib/types").ConfigurableSources
  ): { browserPath: string } => {
    return {
      browserPath: `/api/federated/sources/federated_${extractedSourceType}/credentials/schema`,
    };
  },
  validateFederatedCredentials: (source: string): { browserPath: string } => {
    return {
      browserPath: `/api/federated/sources/federated_${source}/credentials/validate`,
    };
  },
  createFederatedConnection: { browserPath: "/api/federated" },
  updateFederatedConnection: (id: number): { browserPath: string } => {
    return { browserPath: `/api/federated/${id}` };
  },
  loadFederatedConfigurationSchema: (
    connector: import("@/lib/types").ConfigurableSources
  ): { browserPath: string } => {
    return {
      browserPath: `/api/federated/sources/federated_${connector}/configuration/schema`,
    };
  },
  createSlackBot: { browserPath: "/api/manage/admin/slack-app/bots" },
  slackBot: { browserPath: "/api/manage/admin/slack-app/bots" },
  slackChannelConfig: { browserPath: "/api/manage/admin/slack-app/channel" },
  slackBots: { browserPath: "/api/manage/admin/slack-app/bots" },
  slackBotDetail: (botId: number): { browserPath: string } => {
    return {
      browserPath: `${
        integrationsEndpoints.slackBot.browserPath
      }/${encodeURIComponent(botId)}`,
    };
  },
  slackChannelConfigByBot: (botId: number): { browserPath: string } => {
    return {
      browserPath: integrationsEndpoints.slackChannelConfigByEncodedBot(
        encodeURIComponent(botId)
      ).browserPath,
    };
  },
  updateSlackBot: (id: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/slack-app/bots/${id}` };
  },
  fetchDiscordManagedConfig: {
    browserPath: "/api/manage/admin/discord-bot/config",
  },
  disconnectFederatedOAuth: (
    federated_connector_id: number
  ): { browserPath: string } => {
    return { browserPath: `/api/federated/${federated_connector_id}/oauth` };
  },
  slackChannelConfigByEncodedBot: (value0: string): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/slack-app/bots/${value0}/config` };
  },
  fetchSlackBot: (value0: string): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/slack-app/bots/${value0}` };
  },
  discordGuilds: { browserPath: "/api/manage/admin/discord-bot/guilds" },
  discordGuildCatalog: { browserPath: "/api/manage/admin/discord-bot/guilds" },
  discordGuild: (configId: number): { browserPath: string } => {
    return {
      browserPath: `${
        integrationsEndpoints.discordGuildCatalog.browserPath
      }/${encodeURIComponent(configId)}`,
    };
  },
  discordChannels: (guildConfigId: number): { browserPath: string } => {
    return {
      browserPath: integrationsEndpoints.discordGuildChannels(
        encodeURIComponent(guildConfigId)
      ).browserPath,
    };
  },
  gmailCredential: { browserPath: "/api/manage/credential" },
  googleDriveCredential: { browserPath: "/api/manage/credential" },
  gmailAuthorize: (credentialId: number): { browserPath: string } => {
    return {
      browserPath: integrationsEndpoints.authorizeGmail(
        encodeURIComponent(credentialId)
      ).browserPath,
    };
  },
  googleDriveAuthorize: (credentialId: number): { browserPath: string } => {
    return {
      browserPath: integrationsEndpoints.authorizeGoogleDrive(
        encodeURIComponent(credentialId)
      ).browserPath,
    };
  },
  discordGuildChannels: (value0: string): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/discord-bot/guilds/${value0}/channels`,
    };
  },
  authorizeGmail: (value0: string): { browserPath: string } => {
    return { browserPath: `/api/manage/connector/gmail/authorize/${value0}` };
  },
  authorizeGoogleDrive: (value0: string): { browserPath: string } => {
    return {
      browserPath: `/api/manage/connector/google-drive/authorize/${value0}`,
    };
  },
  prepareOAuthAuthorizationRequest: (
    value0: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/oauth/prepare-authorization-request?connector=${value0}`,
    };
  },
  handleOAuthSlackAuthorization: (
    value0: string,
    value1: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/oauth/connector/slack/callback?code=${value0}&state=${value1}`,
    };
  },
  handleOAuthGoogleDriveAuthorization: (
    value0: string,
    value1: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/oauth/connector/google-drive/callback?code=${value0}&state=${value1}`,
    };
  },
  handleOAuthConfluenceAuthorization: (
    value0: string,
    value1: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/oauth/connector/confluence/callback?code=${value0}&state=${value1}`,
    };
  },
  handleOAuthConfluencePrepareFinalization: (
    value0: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/oauth/connector/confluence/accessible-resources?credential_id=${value0}`,
    };
  },
  handleOAuthConfluenceFinalize: (
    value0: string,
    value1: string,
    value2: string,
    value3: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/oauth/connector/confluence/finalize?credential_id=${value0}&cloud_id=${value1}&cloud_name=${value2}&cloud_url=${value3}`,
    };
  },
  connectorOAuthDetails: (source: string): { browserPath: string } => {
    return { browserPath: `/api/connector/oauth/details/${source}` };
  },
  federatedConnectors: { browserPath: "/api/federated" },
  connectorOAuthCallbackBackend: (
    connector: "gmail" | "google-drive"
  ): { backend: import("@/lib/api/http/types").BackendTarget } => ({
    backend: {
      service: "agent" as const,
      path: `/api/v1/manage/connector/${connector}/callback`,
    },
  }),
} as const;
