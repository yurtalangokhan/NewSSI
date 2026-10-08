// System Domain API endpoint paths
// Merged from system and performance modules

// === System endpoints ===

// === Performance endpoints (merged into system) ===

// === System endpoint builders ===

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const systemEndpoints = {
  mailConfigsProxyTarget: (segments: string[] = []) => {
    const suffix = segments.join("/");
    return {
      backend: {
        service: "agent",
        path: `/api/v1/mail-configs${suffix ? `/${suffix}` : ""}`,
      },
    } as const;
  },
  updateEnterpriseTheme: {
    method: "PUT",
    browserPath: "/api/admin/enterprise-settings",
  },
  updateCustomAnalyticsScript: {
    method: "PUT",
    browserPath: "/api/admin/enterprise-settings/custom-analytics-script",
  },
  getEnterpriseSettings: {
    method: "GET",
    backend: { service: "agent", path: "/api/v1/enterprise-settings" },
  },
  getCustomAnalyticsScript: {
    method: "GET",
    backend: {
      service: "agent",
      path: "/api/v1/enterprise-settings/custom-analytics-script",
    },
  },
  version: {
    method: "GET",
    browserPath: "/api/version",
    backend: { service: "agent", path: "/api/v1/version" },
  },
  health: { browserPath: "/api/health" },
  mailConfigs: { browserPath: "/api/mail-configs" },
  mailConfig: (id: string): { browserPath: string } => {
    return { browserPath: `${systemEndpoints.mailConfigs.browserPath}/${id}` };
  },
  mailConfigTest: (id: string): { browserPath: string } => {
    return {
      browserPath: `${systemEndpoints.mailConfig(id).browserPath}/test`,
    };
  },
  userMailSettings: { browserPath: "/api/mail-configs/user-credentials" },
  userMailSettingsTest: {
    browserPath: "/api/mail-configs/user-credentials/test",
  },
  availableMailConfigs: { browserPath: "/api/mail-configs/available" },
  mailConfigsPage: (options?: {
    search?: string;
    page?: number;
    pageSize?: number;
  }): { browserPath: string } => {
    const params = new URLSearchParams();
    if (options?.search?.trim()) params.set("search", options.search.trim());
    if (options?.page !== undefined) params.set("page", String(options.page));
    if (options?.pageSize !== undefined)
      params.set("page_size", String(options.pageSize));
    const query = params.toString();
    return {
      browserPath: query
        ? `${systemEndpoints.mailConfigs.browserPath}?${query}`
        : systemEndpoints.mailConfigs.browserPath,
    };
  },
  queryHistoryList: { browserPath: "/api/admin/query-history/list" },
  queryHistoryExportStatus: {
    browserPath: "/api/admin/query-history/export-status",
  },
  queryHistoryStartExport: {
    browserPath: "/api/admin/query-history/start-export",
  },
  usageReport: { browserPath: "/api/admin/usage-report" },
  tokenRateLimits: { browserPath: "/api/admin/token-rate-limits" },
  tokenRateLimitsGlobal: { browserPath: "/api/admin/token-rate-limits/global" },
  tokenRateLimitsUsers: { browserPath: "/api/admin/token-rate-limits/users" },
  tokenRateLimitsGroups: { browserPath: "/api/admin/token-rate-limits/groups" },
  groupTokenRateLimits: (groupId: number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/token-rate-limits/user-group/${groupId}`,
    };
  },
  analyticsAdminAtlasbot: { browserPath: "/api/analytics/admin/atlasbot" },
  analyticsAdminQuery: { browserPath: "/api/analytics/admin/query" },
  analyticsAdminUser: { browserPath: "/api/analytics/admin/user" },
  analyticsAdminPersonaMessages: {
    browserPath: "/api/analytics/admin/persona/messages",
  },
  analyticsAdminPersonaUniqueUsers: {
    browserPath: "/api/analytics/admin/persona/unique-users",
  },
  analytics: (
    path: string,
    params: Record<string, string | undefined>
  ): { browserPath: string } => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) query.set(key, value);
    }
    const suffix = query.toString();
    return { browserPath: suffix ? `${path}?${suffix}` : path };
  },
  chatSessionHistoryPage: (
    params: URLSearchParams
  ): { browserPath: string } => {
    return {
      browserPath: `${
        systemEndpoints.chatSessionHistoryBase.browserPath
      }?${params.toString()}`,
    };
  },
  searchSettingsCurrent: {
    browserPath: "/api/search-settings/get-current-search-settings",
  },
  searchSettingsSecondary: {
    browserPath: "/api/search-settings/get-secondary-search-settings",
  },
  keycloakSettings: {
    browserPath: "/api/user-service/system-settings/keycloak",
  },
  chatSessionHistory: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `/api/admin/chat-session-history/${encodeURIComponent(
        sessionId
      )}`,
    };
  },
  chatSessionHistoryBase: { browserPath: "/api/admin/chat-session-history" },
  insertGlobalTokenRateLimit: {
    browserPath: "/api/admin/token-rate-limits/global",
  },
  insertUserTokenRateLimit: {
    browserPath: "/api/admin/token-rate-limits/users",
  },
  insertGroupTokenRateLimit: (group_id: number): { browserPath: string } => {
    return {
      browserPath: `${systemEndpoints.tokenRateLimits.browserPath}/user-group/${group_id}`,
    };
  },
  deleteTokenRateLimit: (
    token_rate_limit_id: number
  ): { browserPath: string } => {
    return {
      browserPath: `${systemEndpoints.tokenRateLimits.browserPath}/rate-limit/${token_rate_limit_id}`,
    };
  },
  fetchLogCategories: { browserPath: "/api/admin/long-term-logs" },
  downloadLogCategory: (category: string): { browserPath: string } => {
    return { browserPath: `/api/admin/long-term-logs/${category}/download` };
  },
  uploadEnterpriseLogo: { browserPath: "/api/admin/enterprise-settings/logo" },
  fetchAgentUsageStats: (
    agentId: number,
    pathValue: string,
    pathValue2: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/analytics/assistant/${agentId}/stats?start=${pathValue}&end=${pathValue2}`,
    };
  },
  startQueryHistoryCsvExport: (
    dateRange: { from: Date; to: Date } | undefined
  ): { browserPath: string } => {
    return {
      browserPath: dateRange
        ? `/api/admin/query-history/start-export?start=${dateRange.from.toISOString()}&end=${dateRange.to.toISOString()}`
        : "/api/admin/query-history/start-export",
    };
  },
  checkQueryHistoryCsvExport: (requestId: string): { browserPath: string } => {
    return {
      browserPath: `/api/admin/query-history/export-status?request_id=${requestId}`,
    };
  },
  syncExternalIdentityProvider: (): { browserPath: string } => {
    return {
      browserPath:
        "/api/user-service/system-settings/keycloak/external-idp/sync",
    };
  },
  patchKeycloakConfiguration: (): { browserPath: string } => {
    return { browserPath: "/api/user-service/system-settings/keycloak" };
  },
  patchKeycloakRealmSession: (): { browserPath: string } => {
    return {
      browserPath: "/api/user-service/system-settings/keycloak/realm-session",
    };
  },
  queryHistoryDownload: { browserPath: "/api/admin/query-history/download" },
  chatSessionHistoryCacheKey: (sessionId: string): { browserPath: string } => {
    return { browserPath: `/api/admin/chat-session-history/${sessionId}` };
  },
  usageReportDownload: (
    reportName: string
  ): { browserPath: `/api/admin/usage-report/${string}` } => {
    return { browserPath: `/api/admin/usage-report/${reportName}` };
  },
  logoCacheBusted: (timestamp: number): { browserPath: string } => {
    return { browserPath: `/api/enterprise-settings/logo?u=${timestamp}` };
  },
} as const;
