// Connector/Credential management endpoints

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const datasourcesEndpoints = {
  getKnowledgeSelector: (timestamp?: number) =>
    ({
      method: "GET",
      browserPath: `/api/datasources/knowledge-selector${
        timestamp === undefined ? "" : `?ts=${timestamp}`
      }`,
      backend: {
        service: "rag",
        path: "/api/v1/datasources/knowledge-selector",
      },
    }) as const,
  listConnectors: {
    method: "GET",
    browserPath: "/api/manage/connector",
    backend: { service: "agent", path: "/api/v1/manage/connector" },
  },
  dataSources: { browserPath: "/api/agent/datasources" },
  dataSourceConnectors: { browserPath: "/api/agent/datasources/connectors" },
  sourceConnectors: (search?: string): { browserPath: string } => {
    return {
      browserPath: search
        ? `${
            datasourcesEndpoints.dataSourceConnectors.browserPath
          }?search=${encodeURIComponent(search)}`
        : datasourcesEndpoints.dataSourceConnectors.browserPath,
    };
  },
  datasourceStatus: (id: string): { browserPath: string } => {
    return {
      browserPath: `${datasourcesEndpoints.dataSources.browserPath}/${id}/status`,
    };
  },
  datasourceSyncHistory: (id: string): { browserPath: string } => {
    return {
      browserPath: `${datasourcesEndpoints.dataSources.browserPath}/${id}/sync-history`,
    };
  },
  datasourceScheduleStatus: (id: string): { browserPath: string } => {
    return {
      browserPath: `${datasourcesEndpoints.dataSources.browserPath}/${id}/schedule`,
    };
  },
  connectorStatus: { browserPath: "/api/manage/connector-status" },
  adminCredential: { browserPath: "/api/manage/admin/credential" },
  datasourceDetail: (id: string): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSources.browserPath
      }/${encodeURIComponent(id)}`,
    };
  },
  datasourceDetails: (id: string): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSources.browserPath
      }/${encodeURIComponent(id)}/details`,
    };
  },
  datasourceSync: (
    id: string,
    options: { fullRefresh?: boolean } = {}
  ): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSources.browserPath
      }/${encodeURIComponent(id)}/sync${
        options.fullRefresh ? "?full_refresh=true" : ""
      }`,
    };
  },
  // Describes the streams a datasource's connector can read with its stored
  // configuration; the browser never holds the credentials.
  sourcePreview: { browserPath: "/api/agent/ingest/source-preview" },
  datasourceSchedule: (datasourceId: string): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSources.browserPath
      }/${encodeURIComponent(datasourceId)}/schedule`,
    };
  },
  connectorValidate: (connectorName: string): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSourceConnectors.browserPath
      }/${encodeURIComponent(connectorName)}/validate`,
    };
  },
  connectorStreams: (connectorName: string): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSourceConnectors.browserPath
      }/${encodeURIComponent(connectorName)}/streams`,
    };
  },
  connectorSpec: (connectorName: string): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.dataSourceConnectors.browserPath
      }/${encodeURIComponent(connectorName)}/spec`,
    };
  },
  cCPairInfo: (ccPairId: number): { browserPath: string } => {
    return {
      browserPath: `/api/manage/cc-pair/${encodeURIComponent(ccPairId)}/info`,
    };
  },
  cCPairIndexAttempts: (ccPairId: number): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.cCPairInfo(ccPairId).browserPath
      }/index-attempts`,
    };
  },
  cCPairErrors: (ccPairId: number): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.cCPairInfo(ccPairId).browserPath
      }/errors`,
    };
  },
  ccPairIndexAttemptsPage: (
    ccPairId: number,
    params: URLSearchParams
  ): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.cCPairIndexAttempts(ccPairId).browserPath
      }?${params.toString()}`,
    };
  },
  ccPairErrorsPage: (
    ccPairId: number,
    params: URLSearchParams
  ): { browserPath: string } => {
    return {
      browserPath: `${
        datasourcesEndpoints.cCPairErrors(ccPairId).browserPath
      }?${params.toString()}`,
    };
  },
  connectorFiles: (connectorId: number | string): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/connector/${encodeURIComponent(
        connectorId
      )}/files`,
    };
  },
  submitFiles: { browserPath: "/api/manage/admin/connector/file/upload" },
  uploadDriveAppCredential: {
    browserPath: "/api/manage/admin/connector/google-drive/app-credential",
  },
  uploadDriveServiceAccountKey: {
    browserPath: "/api/manage/admin/connector/google-drive/service-account-key",
  },
  saveDriveServiceAccountCredential: {
    browserPath:
      "/api/manage/admin/connector/google-drive/service-account-credential",
  },
  uploadGmailAppCredential: {
    browserPath: "/api/manage/admin/connector/gmail/app-credential",
  },
  uploadGmailServiceAccountKey: {
    browserPath: "/api/manage/admin/connector/gmail/service-account-key",
  },
  saveGmailServiceAccountCredential: {
    browserPath: "/api/manage/admin/connector/gmail/service-account-credential",
  },
  submitConnectorRequest: { browserPath: "/api/manage/connector-request" },
  fetchConnectorOAuthRedirect: (
    connector: string,
    queryParams: URLSearchParams
  ): { browserPath: string } => {
    return {
      browserPath: `/api/connector/oauth/authorize/${connector}?${queryParams.toString()}`,
    };
  },
  fetchIndexingStatus: {
    browserPath: "/api/manage/admin/connector/indexing-status",
  },
  fetchConnectors: (value0: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/connector?credential=${value0}` };
  },
  googleAppCredential: (
    service: "gmail" | "google-drive"
  ): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/connector/${service}/app-credential`,
    };
  },
  googleServiceAccountKey: (
    service: "gmail" | "google-drive"
  ): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/connector/${service}/service-account-key`,
    };
  },
  createConnector: { browserPath: "/api/manage/admin/connector" },
  createConnectorWithMockCredential: {
    browserPath: "/api/manage/admin/connector-with-mock-credential",
  },
  updateConnectorCredentialPairName: (
    value0: number,
    value1: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/cc-pair/${value0}/name?new_name=${value1}`,
    };
  },
  updateConnectorCredentialPairProperty: (
    value0: number
  ): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/cc-pair/${value0}/property` };
  },
  updateConnector: (value0: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/connector/${value0}` };
  },
  runConnector: { browserPath: "/api/manage/admin/connector/run-once" },
  createCredential: { browserPath: "/api/manage/credential" },
  createCredentialWithPrivateKey: {
    browserPath: "/api/manage/credential/private-key",
  },
  adminDeleteCredential: (value0: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/credential/${value0}` };
  },
  deleteCredential: (value0: number): { browserPath: string } => {
    return { browserPath: `/api/manage/credential/${value0}` };
  },
  linkCredential: (value0: number, value1: number): { browserPath: string } => {
    return {
      browserPath: `/api/manage/connector/${value0}/credential/${value1}`,
    };
  },
  updateCredentialWithPrivateKey: (value0: number): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/credential/private-key/${value0}`,
    };
  },
  swapCredential: { browserPath: "/api/manage/admin/credential/swap" },
  scheduleDeletionJobForConnector: {
    browserPath: "/api/manage/admin/deletion-attempt",
  },
  setCCPairStatus: (value0: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/cc-pair/${value0}/status` };
  },
  updateConnectorFiles: (value0: number): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/connector/${value0}/files/update`,
    };
  },
  connectors: { browserPath: "/api/build/connectors" },
  secondaryFailedIndexingStatus: {
    browserPath:
      "/api/manage/admin/connector/failed-indexing-status?secondary_index=true",
  },
  similarCredentialInfo: (
    source: string,
    editable = false
  ): { browserPath: string } => {
    const base = `/api/manage/admin/similar-credentials/${source}`;
    return { browserPath: editable ? `${base}?get_editable=True` : base };
  },
  ccPairInfoWithQuery: (ccPairId: string | number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/cc-pair/${ccPairId}` };
  },
  connectorFilesCacheKey: (
    connectorId: string | number
  ): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/connector/${connectorId}/files` };
  },
  driveCredentialsCacheKey: {
    browserPath: "/api/manage/admin/connector/google-drive/credentials",
  },
  drivePublicCredentialCacheKey: {
    browserPath: "/api/manage/admin/connector/google-drive/public-credential",
  },
  gmailCredentialsCacheKey: {
    browserPath: "/api/manage/admin/connector/gmail/credentials",
  },
  gmailPublicCredentialCacheKey: {
    browserPath: "/api/manage/admin/connector/gmail/public-credential",
  },
  connectorToolOptions: { browserPath: "/api/agent/datasources/tool-options" },
} as const;
