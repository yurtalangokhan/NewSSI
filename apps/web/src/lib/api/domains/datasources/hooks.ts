"use client";
import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";

import { fetchConnectorToolOptions } from "@/lib/api/domains/datasources/api";

export function useConnectorToolOptions() {
  const { data, error, isLoading } = useSWR(
    datasourcesEndpoints.connectorToolOptions.browserPath,
    fetchConnectorToolOptions
  );
  return { options: data, error, isLoading };
}

import useSWR from "swr";
import { mutate } from "swr";
import { useSWRConfig } from "swr";

import { FetchError } from "@/lib/api/http/errors";
import { toast } from "@/hooks/useToast";
import { AccessType } from "@/lib/types";
import { ValidSources } from "@/lib/types";
import { CCPairBasicInfo } from "@/lib/types";
import type { ConnectorStatus } from "@/lib/types";
import type { Credential } from "@/lib/connectors/credentials";
import type { FileConfig } from "@/lib/connectors/connectors";
import { ConnectorCredentialPairStatus } from "@/lib/api/domains/datasources/types";
import { fetchDataSources } from "@/lib/api/domains/datasources/api";
import { fetchDataSourceConnectors } from "@/lib/api/domains/datasources/api";
import { fetchDatasourceStatus } from "@/lib/api/domains/datasources/api";
import { fetchDatasourceSyncHistory } from "@/lib/api/domains/datasources/api";
import { fetchDatasourceSchedule } from "@/lib/api/domains/datasources/api";
import { fetchPublicCredentials } from "@/lib/api/domains/datasources/api";
import { fetchConnectorStatus } from "@/lib/api/domains/datasources/api";
import { createDatasource as rawCreateDatasource } from "@/lib/api/domains/datasources/api";
import { deleteDatasource as rawDeleteDatasource } from "@/lib/api/domains/datasources/api";
import { syncDatasource as rawSyncDatasource } from "@/lib/api/domains/datasources/api";
import { deleteSchedule as rawDeleteSchedule } from "@/lib/api/domains/datasources/api";
import { fetchConnectorSpec as rawFetchConnectorSpec } from "@/lib/api/domains/datasources/api";
import { scheduleDeletionJobForConnector } from "@/lib/api/domains/datasources/api";
import { setCCPairStatusRequest } from "@/lib/api/domains/datasources/api";
import { uploadFileConnectorFiles } from "@/lib/api/domains/datasources/api";
import { createConnector } from "@/lib/api/domains/datasources/api";
import { createCredential } from "@/lib/api/domains/datasources/api";
import { linkCredential } from "@/lib/api/domains/datasources/api";
import { runConnector } from "@/lib/api/domains/datasources/api";
import type { ConnectorDatasource } from "@/lib/api/domains/datasources/api";
import type { SyncStatusResponse } from "@/lib/api/domains/datasources/api";
import type { SyncAttempt } from "@/lib/api/domains/datasources/api";
import type { ScheduleInfo } from "@/lib/api/domains/datasources/api";
import type { SourceConnectorsResponse } from "@/lib/api/domains/datasources/api";
import type { SourceConnector } from "@/lib/api/domains/datasources/api";
import type { ConnectorSpec } from "@/lib/api/domains/datasources/api";
import { ConnectorIndexingStatusLiteResponse } from "@/lib/types";
import { IndexingStatusRequest } from "@/lib/types";
import { useCallback } from "react";
import { useEffect } from "react";
import { useMemo } from "react";
import { useRef } from "react";
import { useState } from "react";
import { fetchConnectorIndexingStatus } from "@/lib/api/domains/datasources/api";

export const usePublicCredentials = () => {
  const { mutate: mutateCache } = useSWRConfig();
  const swrResponse = useSWR<Credential<any>[]>(
    datasourcesEndpoints.adminCredential.browserPath,
    () => fetchPublicCredentials<Credential<any>[]>()
  );
  return {
    ...swrResponse,
    refreshCredentials: () =>
      mutateCache(datasourcesEndpoints.adminCredential.browserPath),
  };
};

export const useConnectorStatus = (refreshInterval = 30000) => {
  const { mutate: mutateCache } = useSWRConfig();
  const swrResponse = useSWR<ConnectorStatus<any, any>[]>(
    datasourcesEndpoints.connectorStatus.browserPath,
    () => fetchConnectorStatus<ConnectorStatus<any, any>[]>(),
    { refreshInterval }
  );
  return {
    ...swrResponse,
    refreshIndexingStatus: () =>
      mutateCache(datasourcesEndpoints.connectorStatus.browserPath),
  };
};

export const useBasicConnectorStatus = (enabled = true) => {
  const swrResponse = useSWR<CCPairBasicInfo[]>(
    enabled ? datasourcesEndpoints.connectorStatus.browserPath : null,
    () => fetchConnectorStatus<CCPairBasicInfo[]>()
  );
  return {
    ...swrResponse,
    refreshIndexingStatus: () =>
      mutate(datasourcesEndpoints.connectorStatus.browserPath),
  };
};

// Re-export types from client for convenience
export type {
  SourceConnector,
  SourceConnectorsResponse,
  ConnectorDatasource,
  SyncStatusResponse,
  SyncAttempt,
  ScheduleInfo,
  DataSourceDetails,
  StreamInfo,
} from "@/lib/api/domains/datasources/api";

// ── Normalization helpers ──────────────────────────────────────────────────────

const MAX_INLINE_SVG_LENGTH = 24_000;

function isOversizedInlineSvg(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const trimmed = value.trimStart();
  const isSvg =
    trimmed.startsWith("<svg") ||
    trimmed.startsWith("<?xml") ||
    trimmed.includes("<svg");
  return isSvg && value.length > MAX_INLINE_SVG_LENGTH;
}

function normalizeConnector(connector: SourceConnector): SourceConnector {
  const normalized: SourceConnector = { ...connector };
  if (isOversizedInlineSvg(normalized.icon_url)) {
    normalized.icon_url = undefined;
  }
  if (isOversizedInlineSvg(normalized.icon)) {
    normalized.icon = undefined;
  }
  return normalized;
}

function normalizeConnectorsResponse(
  response: SourceConnectorsResponse
): SourceConnectorsResponse {
  const normalizedByCategory = Object.fromEntries(
    Object.entries(response.by_category ?? {}).map(([category, connectors]) => [
      category,
      (connectors ?? []).map(normalizeConnector),
    ])
  );
  return {
    ...response,
    by_category: normalizedByCategory,
    connectors: response.connectors?.map(normalizeConnector),
  };
}

// ── Hooks ────────────────────────────────────────────────────────────────────

export function useSourceConnectors(search?: string) {
  const url = datasourcesEndpoints.sourceConnectors(search).browserPath;

  const { data, error, isLoading, mutate } = useSWR<SourceConnectorsResponse>(
    url,
    () => fetchDataSourceConnectors(search),
    { revalidateOnFocus: false }
  );

  const normalizedData = data ? normalizeConnectorsResponse(data) : null;
  return { data: normalizedData, isLoading, error, mutate };
}

export function useConnectorDatasources() {
  const { data, error, isLoading, mutate } = useSWR<ConnectorDatasource[]>(
    datasourcesEndpoints.dataSources.browserPath,
    fetchDataSources,
    { refreshInterval: 30_000 }
  );
  return { datasources: data ?? [], isLoading, error, mutate };
}

export function useDatasourceStatus(id: string | null, active: boolean) {
  const { data, error, isLoading, mutate } = useSWR<SyncStatusResponse>(
    active && id ? datasourcesEndpoints.datasourceStatus(id).browserPath : null,
    () => fetchDatasourceStatus(id!),
    { refreshInterval: 2_000 }
  );
  return { status: data ?? null, isLoading, error, mutate };
}

export function useDatasourceSyncHistory(id: string | null, open: boolean) {
  const { data, error, isLoading, mutate } = useSWR<SyncAttempt[]>(
    open && id
      ? datasourcesEndpoints.datasourceSyncHistory(id).browserPath
      : null,
    () => fetchDatasourceSyncHistory(id!)
  );
  return { attempts: data ?? [], isLoading, error, mutate };
}

export function useDatasourceSchedule(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<ScheduleInfo>(
    id ? datasourcesEndpoints.datasourceScheduleStatus(id).browserPath : null,
    () => fetchDatasourceSchedule(id!)
  );
  return { schedule: data ?? null, isLoading, error, mutate };
}

// ── Wrapped API functions (with error handling) ────────────────────────────────

export class DatasourceConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DatasourceConflictError";
  }
}

export async function createDatasource(input: {
  name: string;
  config: {
    connector_type: string;
    connector_config: Record<string, unknown>;
    streams?: string[];
    content_fields?: string[];
  };
}): Promise<ConnectorDatasource> {
  try {
    return (await rawCreateDatasource(input)) as ConnectorDatasource;
  } catch (err: unknown) {
    if (err instanceof FetchError && err.status === 409) {
      throw new DatasourceConflictError(
        err.userMessage || "A data source with this name already exists."
      );
    }
    throw err;
  }
}

export async function deleteDatasource(id: string): Promise<void> {
  await rawDeleteDatasource(id);
}

export async function syncDatasource(id: string): Promise<void> {
  await rawSyncDatasource(id);
}

export async function deleteSchedule(datasourceId: string): Promise<void> {
  await rawDeleteSchedule(datasourceId);
}

export async function fetchConnectorSpec(
  connectorName: string
): Promise<ConnectorSpec> {
  try {
    return await rawFetchConnectorSpec(connectorName);
  } catch (err: unknown) {
    if (err instanceof FetchError) {
      throw new Error(
        err.userMessage || `Failed to fetch spec for ${connectorName}`
      );
    }
    throw err;
  }
}

export type {
  ChunkInfo,
  ConnectorSpec,
} from "@/lib/api/domains/datasources/api";

export async function deleteCCPair(
  connectorId: number,
  credentialId: number,
  onCompletion: () => void
): Promise<void> {
  const error = await scheduleDeletionJobForConnector(
    connectorId,
    credentialId
  );
  if (error) {
    toast.error(`Failed to schedule deletion of connector - ${error}`);
  } else {
    toast.success("Scheduled deletion of connector!");
  }
  onCompletion();
}

export async function setCCPairStatus(
  ccPairId: number,
  status: ConnectorCredentialPairStatus,
  onUpdate?: () => void
): Promise<void> {
  try {
    const response = await setCCPairStatusRequest(ccPairId, status);
    if (!response.ok) {
      const { detail } = (await response.json()) as { detail?: string };
      toast.error(`Failed to update connector status - ${detail}`);
      return;
    }
    toast.success(
      status === ConnectorCredentialPairStatus.ACTIVE
        ? "Enabled connector!"
        : "Paused connector!"
    );
    onUpdate?.();
  } catch (error) {
    console.error("Error updating CC pair status:", error);
    toast.error("Failed to update connector status");
  }
}

export async function submitFiles(
  selectedFiles: File[],
  name: string,
  accessType: string,
  groups?: number[]
): Promise<boolean | undefined> {
  const response = await uploadFileConnectorFiles(selectedFiles);
  const responseJson = (await response.json()) as {
    detail?: string;
    file_paths: string[];
    file_names: string[];
    zip_metadata_file_id: string | null;
  };
  if (!response.ok) {
    toast.error(`Unable to upload files - ${responseJson.detail}`);
    return;
  }

  const [connectorError, connector] = await createConnector<FileConfig>({
    name: `FileConnector-${Date.now()}`,
    source: ValidSources.File,
    input_type: "load_state",
    connector_specific_config: {
      file_locations: responseJson.file_paths,
      file_names: responseJson.file_names,
      zip_metadata_file_id: responseJson.zip_metadata_file_id,
    },
    refresh_freq: null,
    prune_freq: null,
    indexing_start: null,
    access_type: accessType,
    groups,
  });
  if (connectorError || !connector) {
    toast.error(`Unable to create connector - ${connectorError}`);
    return;
  }

  const credentialResponse = await createCredential({
    credential_json: {},
    admin_public: true,
    source: ValidSources.File,
    curator_public: true,
    groups,
    name,
  });
  if (!credentialResponse.ok) {
    toast.error(
      `Error creating credential for CC Pair - ${await credentialResponse.text()}`
    );
    return false;
  }
  const credentialId = ((await credentialResponse.json()) as { id: number }).id;
  const credentialResponseResult = await linkCredential(
    connector.id,
    credentialId,
    name,
    accessType as AccessType,
    groups
  );
  if (!credentialResponseResult.ok) {
    const error = (await credentialResponseResult.json()) as {
      detail?: string;
    };
    toast.error(`Unable to link connector to credential - ${error.detail}`);
    return false;
  }

  const runError = await runConnector(connector.id, [0]);
  if (runError) {
    toast.error(`Unable to run connector - ${runError}`);
    return false;
  }
  toast.success("Successfully uploaded files!");
  return true;
}

export const useConnectorIndexingStatusWithPagination = (
  filters: Omit<IndexingStatusRequest, "source" | "source_to_page"> = {},
  refreshInterval = 30000
) => {
  const { mutate } = useSWRConfig();
  //maintains the current page for each source
  const [sourcePages, setSourcePages] = useState<Record<ValidSources, number>>(
    {} as Record<ValidSources, number>
  );
  const [mergedData, setMergedData] = useState<
    ConnectorIndexingStatusLiteResponse[]
  >([]);
  //maintains the loading state for each source
  const [sourceLoadingStates, setSourceLoadingStates] = useState<
    Record<ValidSources, boolean>
  >({} as Record<ValidSources, boolean>);

  //ref to maintain the current source pages for the main request
  const sourcePagesRef = useRef(sourcePages);
  sourcePagesRef.current = sourcePages;

  // Main request that includes current pagination state
  const mainRequest: IndexingStatusRequest = useMemo(
    () => ({
      secondary_index: false,
      access_type_filters: [],
      last_status_filters: [],
      docs_count_operator: null,
      docs_count_value: null,
      ...filters,
    }),
    [filters]
  );

  const swrKey = [
    datasourcesEndpoints.fetchIndexingStatus.browserPath,
    JSON.stringify(mainRequest),
  ];

  // Main data fetch with auto-refresh
  const { data, isLoading, error } = useSWR<
    ConnectorIndexingStatusLiteResponse[]
  >(
    swrKey,
    () => fetchConnectorIndexingStatus(mainRequest, sourcePagesRef.current),
    {
      refreshInterval,
    }
  );

  // Update merged data when main data changes
  useEffect(() => {
    if (data) {
      setMergedData(data);
    }
  }, [data]);

  // Function to handle page changes for a specific source
  const handlePageChange = useCallback(
    async (source: ValidSources, page: number) => {
      // Update the source page state
      setSourcePages((prev) => ({ ...prev, [source]: page }));

      const sourceRequest: IndexingStatusRequest = {
        ...filters,
        source: source,
        source_to_page: { [source]: page } as Record<ValidSources, number>,
      };
      setSourceLoadingStates((prev) => ({ ...prev, [source]: true }));

      try {
        const sourceData = await fetchConnectorIndexingStatus(sourceRequest);
        if (sourceData && sourceData.length > 0) {
          setMergedData((prevData) =>
            prevData
              .map((existingSource) =>
                existingSource.source === source
                  ? sourceData[0]
                  : existingSource
              )
              .filter(
                (item): item is ConnectorIndexingStatusLiteResponse =>
                  item !== undefined
              )
          );
        }
      } catch (error) {
        console.error(
          `Failed to fetch page ${page} for source ${source}:`,
          error
        );
      } finally {
        setSourceLoadingStates((prev) => ({ ...prev, [source]: false }));
      }
    },
    [filters]
  );

  // Function to refresh all data (maintains current pagination)
  const refreshAllData = useCallback(() => {
    mutate(swrKey);
  }, [mutate, swrKey]);

  // Reset pagination when filters change (but not search)
  const resetPagination = useCallback(() => {
    setSourcePages({} as Record<ValidSources, number>);
  }, []);

  return {
    data: mergedData,
    isLoading,
    error,
    handlePageChange,
    sourcePages,
    sourceLoadingStates,
    refreshAllData,
    resetPagination,
  };
};

/**
 * Hook for fetching connector-credential pairs (CC Pairs).
 *
 * Retrieves all connector-credential pairs configured in the system. CC Pairs
 * represent connections between data sources (connectors) and their authentication
 * credentials, used for indexing content from various sources like Confluence,
 * Slack, Google Drive, etc. Uses SWR for caching and automatic revalidation.
 *
 * @returns Object containing:
 *   - ccPairs: Array of CCPairBasicInfo objects
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Error object if the fetch failed
 *   - refetch: Function to manually reload CC pairs
 *
 * @example
 * ```tsx
 * // Display list of connected data sources
 * const ConnectorList = () => {
 *   const { ccPairs, isLoading, error } = useCCPairs();
 *
 *   if (isLoading) return <Spinner />;
 *   if (error) return <Error message="Failed to load connectors" />;
 *
 *   return (
 *     <ul>
 *       {ccPairs.map(pair => (
 *         <li key={pair.id}>
 *           {pair.name} - {pair.source}
 *         </li>
 *       ))}
 *     </ul>
 *   );
 * };
 * ```
 *
 * @example
 * ```tsx
 * // Filter connectors by source type
 * const SlackConnectors = () => {
 *   const { ccPairs } = useCCPairs();
 *
 *   const slackPairs = ccPairs.filter(pair => pair.source === 'slack');
 *
 *   return <ConnectorGrid connectors={slackPairs} />;
 * };
 * ```
 *
 * @example
 * ```tsx
 * // Refresh list after connecting a new source
 * const ConnectSourceButton = () => {
 *   const { refetch } = useCCPairs();
 *
 *   const handleConnect = async () => {
 *     await connectNewSource();
 *     refetch(); // Refresh the list
 *   };
 *
 *   return <Button onClick={handleConnect}>Connect Source</Button>;
 * };
 * ```
 */
export function useCCPairs(enabled: boolean = true) {
  const { data, error, isLoading, mutate } = useSWR<CCPairBasicInfo[]>(
    enabled ? datasourcesEndpoints.connectorStatus.browserPath : null,
    () => fetchConnectorStatus<CCPairBasicInfo[]>()
  );

  return {
    ccPairs: data ?? [],
    isLoading: enabled && isLoading,
    error,
    refetch: mutate,
  };
}
