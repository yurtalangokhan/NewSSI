import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";

import { Connector, ConnectorBase } from "@/lib/connectors/connectors";
import { getErrorMsg } from "@/lib/fetchUtils";
import {
  CredentialBase,
  CredentialWithPrivateKey,
} from "@/lib/connectors/credentials";
import { AccessType, ProcessingMode } from "@/lib/types";
import { TypedFile } from "@/lib/connectors/fileTypes";
import {
  CREDENTIAL_NAME,
  CREDENTIAL_SOURCE,
  CREDENTIAL_UPLOADED_FILE,
  CREDENTIAL_FIELD_KEY,
  CREDENTIAL_TYPE_DEFINITION_KEY,
  CREDENTIAL_JSON,
} from "@/lib/constants";
import { ConnectorCredentialPairStatus } from "@/lib/api/domains/datasources/types";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";
import { parseResponseModel } from "@/lib/api/responseModel";

async function fetchAgentScheduleJson<T>(
  input: RequestInfo | URL,
  options?: RequestInit
): Promise<T> {
  return apiRequest(input, options).then(parseResponseModel<T>);
}

async function fetchJson<T>(
  input: RequestInfo | URL,
  options?: RequestInit
): Promise<T> {
  return apiRequest(input, options).then(parseResponseModel<T>);
}

async function fetchDatasourceSWRJson<T>(path: string): Promise<T> {
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

export const fetchBuildConnectors = <T>() =>
  fetchDatasourceSWRJson<T>(datasourcesEndpoints.connectors.browserPath);
export const fetchSimilarCredentials = <T>(source: string, editable = false) =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.similarCredentialInfo(source, editable).browserPath
  );
export const fetchAllConnectors = <T>() =>
  fetchDatasourceSWRJson<T>(datasourcesEndpoints.listConnectors.browserPath);
export const fetchSecondaryFailedIndexingStatus = <T>() =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.secondaryFailedIndexingStatus.browserPath
  );
export const fetchGoogleAppCredential = <T>(
  service: "gmail" | "google-drive"
) =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.googleAppCredential(service).browserPath
  );
export const fetchGoogleServiceAccountKey = <T>(
  service: "gmail" | "google-drive"
) =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.googleServiceAccountKey(service).browserPath
  );
export const fetchConnectorsByCredential = <T>(credentialId: number) =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.fetchConnectors(credentialId).browserPath
  );
export const fetchCCPairIndexAttemptsPage = <T>(
  ccPairId: number,
  params: URLSearchParams
) =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.ccPairIndexAttemptsPage(ccPairId, params).browserPath
  );
export const fetchCCPairErrorsPage = <T>(
  ccPairId: number,
  params: URLSearchParams
) =>
  fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.ccPairErrorsPage(ccPairId, params).browserPath
  );

export function fetchDataSources() {
  return fetchJson<ConnectorDatasource[]>(
    datasourcesEndpoints.dataSources.browserPath
  );
}

// ── Types ────────────────────────────────────────────────────────────────────────

export interface SourceConnector {
  name: string;
  display_name: string;
  category?: string;
  documentation_url?: string;
  icon?: string;
  icon_url?: string;
  is_available?: boolean;
}

export interface SourceConnectorsResponse {
  categories: string[];
  category_labels: Record<string, string>;
  by_category: Record<string, SourceConnector[]>;
  total: number;
  connectors?: SourceConnector[];
}

export type JSONSchema = Record<string, unknown>;

export interface ConnectorSpec {
  name: string;
  display_name: string;
  connection_specification: JSONSchema;
  documentation_url?: string;
  supported_sync_modes?: string[];
}

export interface StreamInfo {
  name: string;
}

export type SyncStatus =
  | "idle"
  | "starting"
  | "syncing"
  | "completed"
  | "error";

export interface ConnectorDatasource {
  id: string;
  name: string;
  connector_type: string;
  connector_display_name: string;
  streams?: string[];
  sync_status?: SyncStatus;
  sync_progress?: number;
  document_count?: number;
  created_at?: string;
  last_synced_at?: string;
  last_error?: string;
}

export interface ChunkInfo {
  content: string;
  char_count: number;
  token_count: number;
  word_count: number;
  source?: string;
  stream?: string;
  connector_type?: string;
  metadata?: Record<string, unknown>;
}

export interface ScheduleInfo {
  id: string;
  datasource_id: string;
  cron_expression: string;
  preset: string;
  enabled: boolean;
  update_graph_rag: boolean;
  timezone: string;
  next_run_at?: string;
  last_run_at?: string;
  last_run_status?: string;
  created_at?: string;
  updated_at?: string;
}

export interface DataSourceDetails extends ConnectorDatasource {
  config?: Record<string, unknown>;
  chunk_count?: number;
  chunks?: ChunkInfo[];
  avg_chunk_tokens?: number;
  avg_chunk_chars?: number;
  sync_mode?: string;
  destination_sync_mode?: string;
  schedule?: ScheduleInfo;
  graph_rag_available?: boolean;
}

export interface SyncStatusResponse {
  id: string;
  sync_status: SyncStatus;
  sync_progress: number;
  last_synced_at?: string;
  last_error?: string;
  graph_update_status?: string;
  queue_position?: number;
  is_active: boolean;
  schedule?: {
    enabled: boolean;
    cron_expression?: string;
    next_run_at?: string;
    update_graph_rag: boolean;
  };
}

export interface SyncAttempt {
  id: string;
  status:
    | "succeeded"
    | "failed"
    | "cancelled"
    | "running"
    | "pending"
    | "incomplete"
    | "unknown";
  created_at?: number;
  updated_at?: number;
  duration_seconds?: number;
  bytes_synced?: number;
  records_synced?: number;
  error_message?: string | null;
}

export interface CreateDatasourceInput {
  name: string;
  config: {
    connector_type: string;
    connector_config: Record<string, unknown>;
    streams?: string[];
    content_fields?: string[];
  };
}

export interface UpdateDatasourceInput {
  name?: string;
  connector_config?: Record<string, unknown>;
  streams?: string[];
  sync_mode?: string;
  destination_sync_mode?: string;
}

export interface SyncScheduleInput {
  cron_expression: string;
  preset: string;
  enabled: boolean;
  update_graph_rag: boolean;
  timezone: string;
}

// ── Client functions ─────────────────────────────────────────────────────────

export function fetchDataSourceConnectors(search?: string) {
  return fetchJson<SourceConnectorsResponse>(
    datasourcesEndpoints.sourceConnectors(search).browserPath
  );
}

export function fetchDatasourceStatus(id: string) {
  return fetchJson<SyncStatusResponse>(
    datasourcesEndpoints.datasourceStatus(id).browserPath
  );
}

export function fetchDatasourceSyncHistory(id: string) {
  return fetchJson<SyncAttempt[]>(
    datasourcesEndpoints.datasourceSyncHistory(id).browserPath
  );
}

export function fetchDatasourceSchedule(id: string) {
  return fetchAgentScheduleJson<ScheduleInfo>(
    datasourcesEndpoints.datasourceScheduleStatus(id).browserPath
  );
}

export function createDatasource(input: CreateDatasourceInput) {
  return fetchJson<ConnectorDatasource>(
    datasourcesEndpoints.dataSources.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
}

export function updateDatasource(id: string, input: UpdateDatasourceInput) {
  return fetchJson<DataSourceDetails>(
    datasourcesEndpoints.datasourceDetail(id).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
}

export function deleteDatasource(id: string) {
  return fetchJson<unknown>(
    datasourcesEndpoints.datasourceDetail(id).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function getDatasourceDetails(
  id: string,
  page = 1,
  pageSize = 20
): Promise<DataSourceDetails> {
  return fetchJson<DataSourceDetails>(
    `${
      datasourcesEndpoints.datasourceDetails(id).browserPath
    }?page=${page}&page_size=${pageSize}`
  );
}

export function syncDatasource(
  id: string,
  options: { fullRefresh?: boolean } = {}
) {
  return fetchJson<unknown>(
    datasourcesEndpoints.datasourceSync(id, options).browserPath,
    {
      method: "POST",
    }
  );
}

export interface SourcePreviewResponse {
  datasource_id: string;
  source_name?: string;
  connector_type?: string;
  streams: { name: string }[];
  note?: string;
}

/** The streams the datasource's connector can read with its stored configuration. */
export function fetchSourcePreview(
  datasourceId: string
): Promise<SourcePreviewResponse> {
  return fetchJson<SourcePreviewResponse>(
    datasourcesEndpoints.sourcePreview.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ datasource_id: datasourceId }),
    }
  );
}

export function createSchedule(datasourceId: string, input: SyncScheduleInput) {
  return fetchAgentScheduleJson<ScheduleInfo>(
    datasourcesEndpoints.datasourceSchedule(datasourceId).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
}

export function updateSchedule(
  datasourceId: string,
  input: Partial<SyncScheduleInput>
) {
  return fetchAgentScheduleJson<ScheduleInfo>(
    datasourcesEndpoints.datasourceSchedule(datasourceId).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
}

export function deleteSchedule(datasourceId: string) {
  return fetchAgentScheduleJson<unknown>(
    datasourcesEndpoints.datasourceSchedule(datasourceId).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function validateConnectorConfig(
  connectorName: string,
  config: Record<string, unknown>
): Promise<{ valid: boolean; message: string }> {
  return fetchJson<{ valid: boolean; message: string }>(
    datasourcesEndpoints.connectorValidate(connectorName).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );
}

export interface StreamInfo {
  name: string;
}

export function fetchConnectorStreams(
  connectorName: string,
  config: Record<string, unknown>
): Promise<StreamInfo[]> {
  return fetchJson<StreamInfo[]>(
    datasourcesEndpoints.connectorStreams(connectorName).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );
}

export function fetchConnectorSpec(
  connectorName: string
): Promise<ConnectorSpec> {
  return fetchJson<ConnectorSpec>(
    datasourcesEndpoints.connectorSpec(connectorName).browserPath
  );
}

// ============================================================================
// Additional connector/credential management functions
// ============================================================================

export function fetchConnectorStatus<T>(): Promise<T> {
  return fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.connectorStatus.browserPath
  );
}

export function fetchCCPairFullInfo<T>(ccPairId: number): Promise<T> {
  return fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.cCPairInfo(ccPairId).browserPath
  );
}

export function fetchConnectorFiles<T>(
  connectorId: number | string
): Promise<T> {
  return fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.connectorFiles(connectorId).browserPath
  );
}

export function fetchPublicCredentials<T = unknown[]>(): Promise<T> {
  return fetchDatasourceSWRJson<T>(
    datasourcesEndpoints.adminCredential.browserPath
  );
}

// Folded datasource operations (behavior-preserving)
async function handleJsonResponse<T>(
  response: Response
): Promise<[string | null, T | null]> {
  if (response.ok) {
    const data = await parseJsonResponse<T>(response);
    return [null, data ?? null];
  }
  const parsedError = await parseApiErrorResponse(response);
  return [parsedError?.userMessage ?? "Unknown error", null];
}

export async function createConnector<T>(
  connector: ConnectorBase<T>
): Promise<[string | null, Connector<T> | null]> {
  const response = await apiRequest(
    datasourcesEndpoints.createConnector.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(connector),
    }
  );
  return handleJsonResponse<Connector<T>>(response);
}

function writeConnector<T>(
  path: string,
  method: "POST" | "PATCH",
  connector: ConnectorBase<T>
): Promise<Response> {
  return apiRequest(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(connector),
  });
}

export function createConnectorResponse<T>(
  connector: ConnectorBase<T>
): Promise<Response> {
  return writeConnector(
    datasourcesEndpoints.createConnector.browserPath,
    "POST",
    connector
  );
}

export function updateConnectorResponse<T>(
  connectorId: number,
  connector: ConnectorBase<T>
): Promise<Response> {
  return writeConnector(
    datasourcesEndpoints.updateConnector(connectorId).browserPath,
    "PATCH",
    connector
  );
}

export function createConnectorWithMockCredential<T>(
  connector: ConnectorBase<T>
): Promise<Response> {
  return writeConnector(
    datasourcesEndpoints.createConnectorWithMockCredential.browserPath,
    "POST",
    connector
  );
}

export function updateConnectorWithMockCredential<T>(
  connector: ConnectorBase<T>
): Promise<Response> {
  return writeConnector(
    datasourcesEndpoints.createConnectorWithMockCredential.browserPath,
    "PATCH",
    connector
  );
}

export async function updateConnectorCredentialPairName(
  ccPairId: number,
  newName: string
): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.updateConnectorCredentialPairName(
      ccPairId,
      encodeURIComponent(newName)
    ).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
    }
  );
}

export async function updateConnectorCredentialPairProperty(
  ccPairId: number,
  name: string,
  value: string
): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.updateConnectorCredentialPairProperty(ccPairId)
      .browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        value: value,
      }),
    }
  );
}

export async function deleteConnector(
  connectorId: number
): Promise<string | null> {
  const response = await apiRequest(
    datasourcesEndpoints.updateConnector(connectorId).browserPath,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    }
  );
  if (response.ok) {
    return null;
  }
  return (await getErrorMsg(response)) ?? "Unknown error";
}

export async function runConnector(
  connectorId: number,
  credentialIds: number[],
  fromBeginning: boolean = false
): Promise<string | null> {
  const response = await apiRequest(
    datasourcesEndpoints.runConnector.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        connector_id: connectorId,
        credentialIds,
        from_beginning: fromBeginning,
      }),
    }
  );
  if (!response.ok) {
    return (await getErrorMsg(response)) ?? "Unknown error";
  }
  return null;
}

export async function createCredential(credential: CredentialBase<unknown>) {
  return await apiRequest(datasourcesEndpoints.createCredential.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(credential),
  });
}

export async function createCredentialWithPrivateKey(
  credential: CredentialWithPrivateKey<unknown>
) {
  const formData = new FormData();
  formData.append(CREDENTIAL_JSON, JSON.stringify(credential.credential_json));
  formData.append("admin_public", credential.admin_public.toString());
  formData.append(
    "curator_public",
    credential.curator_public?.toString() || "false"
  );
  if (credential.groups && credential.groups.length > 0) {
    credential.groups.forEach((group) => {
      formData.append("groups", String(group));
    });
  }
  formData.append(CREDENTIAL_NAME, credential.name || "");
  formData.append(CREDENTIAL_SOURCE, credential.source);
  if (credential.private_key) {
    formData.append(CREDENTIAL_UPLOADED_FILE, credential.private_key.file);
    formData.append(CREDENTIAL_FIELD_KEY, credential.private_key.fieldKey);
    formData.append(
      CREDENTIAL_TYPE_DEFINITION_KEY,
      credential.private_key.typeDefinition.category
    );
  }
  return await apiRequest(
    datasourcesEndpoints.createCredentialWithPrivateKey.browserPath,
    {
      method: "POST",
      body: formData,
    }
  );
}

export async function adminDeleteCredential<T>(credentialId: number) {
  return await apiRequest(
    datasourcesEndpoints.adminDeleteCredential(credentialId).browserPath,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
}

export async function deleteCredential<T>(
  credentialId: number,
  force?: boolean
) {
  return await apiRequest(
    datasourcesEndpoints.deleteCredential(credentialId).browserPath,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
}

export function linkCredential(
  connectorId: number,
  credentialId: number,
  name?: string,
  accessType?: AccessType,
  groups?: number[],
  autoSyncOptions?: Record<string, unknown>,
  processingMode?: ProcessingMode
) {
  return apiRequest(
    datasourcesEndpoints.linkCredential(connectorId, credentialId).browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: name || null,
        access_type: accessType !== undefined ? accessType : "public",
        groups: groups || null,
        auto_sync_options: autoSyncOptions || null,
        processing_mode: processingMode || "REGULAR",
      }),
    }
  );
}

export function updateCredential(
  credentialId: number,
  newDetails: Record<string, unknown> & { name: string }
) {
  const name = newDetails.name;
  const details = Object.fromEntries(
    Object.entries(newDetails).filter(
      ([key, value]) => key !== CREDENTIAL_NAME && value !== ""
    )
  );
  return apiRequest(
    datasourcesEndpoints.adminDeleteCredential(credentialId).browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: name,
        credential_json: details,
      }),
    }
  );
}

export function updateCredentialWithPrivateKey(
  credentialId: number,
  newDetails: Record<string, unknown> & { name: string },
  privateKey: TypedFile
) {
  const name = newDetails.name;
  const details = Object.fromEntries(
    Object.entries(newDetails).filter(
      ([key, value]) => key !== CREDENTIAL_NAME && value !== ""
    )
  );
  const formData = new FormData();
  formData.append(CREDENTIAL_NAME, name);
  formData.append(CREDENTIAL_JSON, JSON.stringify(details));
  formData.append(CREDENTIAL_UPLOADED_FILE, privateKey.file);
  formData.append(CREDENTIAL_FIELD_KEY, privateKey.fieldKey);
  formData.append(
    CREDENTIAL_TYPE_DEFINITION_KEY,
    privateKey.typeDefinition.category
  );
  return apiRequest(
    datasourcesEndpoints.updateCredentialWithPrivateKey(credentialId)
      .browserPath,
    {
      method: "PUT",
      body: formData,
    }
  );
}

export function swapCredential(
  newCredentialId: number,
  connectorId: number,
  accessType: AccessType
) {
  return apiRequest(datasourcesEndpoints.swapCredential.browserPath, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      new_credential_id: newCredentialId,
      connector_id: connectorId,
      access_type: accessType,
    }),
  });
}

export async function scheduleDeletionJobForConnector(
  connectorId: number,
  credentialId: number
) {
  const response = await apiRequest(
    datasourcesEndpoints.scheduleDeletionJobForConnector.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        connector_id: connectorId,
        credential_id: credentialId,
      }),
    }
  );
  if (response.ok) {
    return null;
  }
  return (await getErrorMsg(response)) ?? "Unknown error";
}

export function setCCPairStatusRequest(
  ccPairId: number,
  ccPairStatus: ConnectorCredentialPairStatus
): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.setCCPairStatus(ccPairId).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: ccPairStatus }),
    }
  );
}

export async function updateConnectorFiles(
  connectorId: number,
  fileIdsToRemove: string[],
  filesToAdd: File[]
): Promise<void> {
  const formData = new FormData();
  formData.append("file_ids_to_remove", JSON.stringify(fileIdsToRemove));
  filesToAdd.forEach((file) => formData.append("files", file));
  const response = await apiRequest(
    datasourcesEndpoints.updateConnectorFiles(connectorId).browserPath,
    { method: "POST", body: formData }
  );
  if (!response.ok) {
    const error = (await response.json()) as { detail?: string };
    throw new Error(
      `Failed to update connector files (${response.status}): ${
        error.detail || "Unknown error"
      }`
    );
  }
}

export function uploadFileConnectorFiles(
  selectedFiles: File[]
): Promise<Response> {
  const formData = new FormData();
  selectedFiles.forEach((file) => {
    formData.append("files", file);
  });
  return apiRequest(datasourcesEndpoints.submitFiles.browserPath, {
    method: "POST",
    body: formData,
  });
}

export function uploadDriveAppCredential(body: string): Promise<Response> {
  return apiRequest(datasourcesEndpoints.uploadDriveAppCredential.browserPath, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: body,
  });
}

export function deleteDriveAppCredential(): Promise<Response> {
  return apiRequest(datasourcesEndpoints.uploadDriveAppCredential.browserPath, {
    method: "DELETE",
  });
}

export function deleteDriveServiceAccountKey(): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.uploadDriveServiceAccountKey.browserPath,
    {
      method: "DELETE",
    }
  );
}

export function uploadDriveServiceAccountKey(body: string): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.uploadDriveServiceAccountKey.browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: body,
    }
  );
}

export function saveDriveServiceAccountCredential(payload: {
  google_primary_admin: string;
}): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.saveDriveServiceAccountCredential.browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function uploadGmailAppCredential(body: string): Promise<Response> {
  return apiRequest(datasourcesEndpoints.uploadGmailAppCredential.browserPath, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: body,
  });
}

export function deleteGmailAppCredential(): Promise<Response> {
  return apiRequest(datasourcesEndpoints.uploadGmailAppCredential.browserPath, {
    method: "DELETE",
  });
}

export function deleteGmailServiceAccountKey(): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.uploadGmailServiceAccountKey.browserPath,
    {
      method: "DELETE",
    }
  );
}

export function uploadGmailServiceAccountKey(body: string): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.uploadGmailServiceAccountKey.browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: body,
    }
  );
}

export function saveGmailServiceAccountCredential(payload: {
  google_primary_admin: string;
}): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.saveGmailServiceAccountCredential.browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function uploadGoogleSiteFile(body: FormData): Promise<Response> {
  return apiRequest(datasourcesEndpoints.submitFiles.browserPath, {
    method: "POST",
    body: body,
  });
}

export function submitConnectorRequest(payload: {
  connector_name: string;
}): Promise<Response> {
  return apiRequest(datasourcesEndpoints.submitConnectorRequest.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function fetchKnowledgeSelector<T>(pathValue: number): Promise<T> {
  const response = await apiRequest(
    datasourcesEndpoints.getKnowledgeSelector(pathValue).browserPath,
    {
      cache: "no-store",
      headers: { "X-Language": i18n.language },
    }
  );
  return parseResponseModel<T>(response);
}

export function fetchConnectorOAuthRedirectResponse(
  connector: string,
  queryParams: URLSearchParams
): Promise<Response> {
  return apiRequest(
    datasourcesEndpoints.fetchConnectorOAuthRedirect(connector, queryParams)
      .browserPath
  );
}

export function fetchIndexingStatusResponse(payload: {
  secondary_index: boolean;
  access_type_filters: string[];
  last_status_filters: string[];
  docs_count_operator: ">" | "<" | "=" | null;
  docs_count_value: number | null;
  source_to_page: Record<import("@/lib/types").ValidSources, number> | {};
  source?: import("@/lib/types").ValidSources | undefined;
  get_all_connectors?: boolean | undefined;
}): Promise<Response> {
  return apiRequest(datasourcesEndpoints.fetchIndexingStatus.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

import {
  ValidSources,
  ConnectorIndexingStatusLiteResponse,
  IndexingStatusRequest,
} from "@/lib/types";

export const fetchConnectorIndexingStatus = async (
  request: IndexingStatusRequest = {},
  sourcePages: Record<ValidSources, number> | null = null
): Promise<ConnectorIndexingStatusLiteResponse[]> => {
  const response = await fetchIndexingStatusResponse({
    secondary_index: false,
    access_type_filters: [],
    last_status_filters: [],
    docs_count_operator: null,
    docs_count_value: null,
    source_to_page: sourcePages || {}, // Use current pagination state
    ...request,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json();
};

import type { ConnectorToolOption } from "@/lib/api/domains/datasources/types";
import i18n from "@/i18n/config";

export function fetchConnectorToolOptions(): Promise<ConnectorToolOption[]> {
  return apiRequest(datasourcesEndpoints.connectorToolOptions.browserPath, {
    headers: { "X-Language": i18n.language },
  }).then(parseResponseModel<ConnectorToolOption[]>);
}
