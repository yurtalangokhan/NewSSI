/**
 * Airbyte integration types and API functions.
 *
 * All API calls go through the /agent proxy which forwards to agent-service.
 * Pattern mirrors lib/hooks.ts and lib/connector.ts from the Onyx codebase.
 */
import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";

// ============================================================================
// Types
// ============================================================================

export interface AirbyteConnector {
  name: string;
  display_name: string;
  source_definition_id: string;
  docker_image_tag?: string;
  documentation_url?: string;
  icon?: string;
  icon_url?: string;
}

export interface AirbyteConnectorsResponse {
  categories: string[];
  category_labels: Record<string, string>;
  by_category: Record<string, AirbyteConnector[]>;
  total: number;
  /** Present when ?search= query param is used */
  connectors?: AirbyteConnector[];
}

/** Raw JSON Schema object (subset used by Airbyte specs) */
export type JSONSchema = Record<string, unknown>;

export interface ConnectorSpec {
  name: string;
  display_name: string;
  source_definition_id: string;
  connection_specification: JSONSchema;
  documentation_url?: string;
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

export interface AirbyteDatasource {
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

export interface DataSourceDetails extends AirbyteDatasource {
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

// ============================================================================
// SWR Hooks
// ============================================================================

export function useAirbyteConnectors(search?: string) {
  const url = search
    ? `/datasources/connectors?search=${encodeURIComponent(search)}`
    : "/datasources/connectors";

  const { data, error, isLoading, mutate } =
    useSWR<AirbyteConnectorsResponse>(url, errorHandlingFetcher);

  return {
    data: data ?? null,
    isLoading,
    error,
    mutate,
  };
}

export function useAirbyteDatasources() {
  const { data, error, isLoading, mutate } = useSWR<AirbyteDatasource[]>(
    "/datasources",
    errorHandlingFetcher,
    { refreshInterval: 30_000 }
  );

  return {
    datasources: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useDatasourceStatus(id: string | null, active: boolean) {
  const { data, error, isLoading, mutate } = useSWR<SyncStatusResponse>(
    active && id ? `/datasources/${id}/status` : null,
    errorHandlingFetcher,
    { refreshInterval: 2_000 }
  );

  return { status: data ?? null, isLoading, error, mutate };
}

export function useDatasourceSchedule(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<ScheduleInfo>(
    id ? `/datasources/${id}/schedule` : null,
    errorHandlingFetcher
  );

  return { schedule: data ?? null, isLoading, error, mutate };
}

// ============================================================================
// API Functions
// ============================================================================

export async function fetchConnectorSpec(
  connectorName: string
): Promise<ConnectorSpec> {
  const res = await fetch(
    `/datasources/connectors/${encodeURIComponent(connectorName)}/spec`
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch spec for ${connectorName}`);
  }
  return res.json();
}

export async function validateConnectorConfig(
  connectorName: string,
  config: Record<string, unknown>
): Promise<{ valid: boolean; message: string }> {
  const res = await fetch(
    `/datasources/connectors/${encodeURIComponent(connectorName)}/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );
  return res.json();
}

export async function fetchConnectorStreams(
  connectorName: string,
  config: Record<string, unknown>
): Promise<StreamInfo[]> {
  const res = await fetch(
    `/datasources/connectors/${encodeURIComponent(connectorName)}/streams`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to discover streams");
  }
  return res.json();
}

export class DatasourceConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DatasourceConflictError";
  }
}

export async function createDatasource(
  input: CreateDatasourceInput
): Promise<AirbyteDatasource> {
  const res = await fetch("/datasources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    if (res.status === 409) {
      throw new DatasourceConflictError(
        err?.detail || "A data source with this name already exists."
      );
    }
    throw new Error(err?.detail || "Failed to create data source");
  }
  return res.json();
}

export async function updateDatasource(
  id: string,
  input: UpdateDatasourceInput
): Promise<DataSourceDetails> {
  const res = await fetch(`/datasources/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to update data source");
  }
  return res.json();
}

export async function deleteDatasource(id: string): Promise<void> {
  const res = await fetch(`/datasources/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to delete data source");
  }
}

export async function syncDatasource(id: string): Promise<void> {
  const res = await fetch(`/datasources/${id}/sync`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to trigger sync");
  }
}

export async function createSchedule(
  datasourceId: string,
  input: SyncScheduleInput
): Promise<ScheduleInfo> {
  const res = await fetch(
    `/datasources/${datasourceId}/schedule`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to create schedule");
  }
  return res.json();
}

export async function updateSchedule(
  datasourceId: string,
  input: Partial<SyncScheduleInput>
): Promise<ScheduleInfo> {
  const res = await fetch(
    `/datasources/${datasourceId}/schedule`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to update schedule");
  }
  return res.json();
}

export async function deleteSchedule(datasourceId: string): Promise<void> {
  const res = await fetch(
    `/datasources/${datasourceId}/schedule`,
    { method: "DELETE" }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to delete schedule");
  }
}


