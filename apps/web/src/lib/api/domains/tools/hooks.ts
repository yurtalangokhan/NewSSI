"use client";
import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";

import useSWR from "swr";
import { useTranslation } from "react-i18next";
import { ToolSnapshot } from "@/lib/tools/interfaces";
import { fetchAvailableTools } from "./api";

import { FetchError } from "@/lib/api/http/errors";
import { fetchBuiltInTools } from "./api";

import { fetchCodeInterpreterHealth } from "./api";
import { fetchCodeInterpreterStatus } from "./api";

import { fetchMcpServers } from "./api";
import { MCPServersResponse } from "@/lib/tools/interfaces";

import { fetchMcpServersForAgent } from "./api";

import { fetchOpenApiTools } from "./api";

import { KeyedMutator } from "swr";
import { fetchMcpServerToolsSnapshots } from "./api";
import { getActionIcon } from "@/lib/tools/mcpUtils";
import { MCPServer } from "@/lib/tools/interfaces";
import { MCPTool } from "@/lib/tools/interfaces";
import i18n from "@/i18n/config";

/**
 * Hook to fetch all available tools from the backend.
 *
 * This hook fetches the complete list of tools that can be used with agents,
 * including built-in tools (SearchTool, ImageGenerationTool, WebSearchTool, PythonTool)
 * and any dynamically configured tools (MCP servers, OpenAPI tools).
 *
 * @example
 * ```tsx
 * const { tools, isLoading, error, refresh } = useAvailableTools();
 *
 * if (isLoading) return <Loading />;
 * if (error) return <Error />;
 *
 * const imageGenTool = tools.find(t => t.in_code_tool_id === "ImageGenerationTool");
 * const isImageGenAvailable = !!imageGenTool;
 * ```
 */
export function useAvailableTools() {
  const { i18n } = useTranslation();
  const { data, error, mutate } = useSWR<ToolSnapshot[]>(
    [toolsEndpoints.tool.browserPath, i18n.language],
    () => fetchAvailableTools(),
    {
      revalidateOnFocus: true,
    }
  );

  return {
    tools: data ?? [],
    isLoading: !error && !data,
    error,
    refresh: mutate,
  };
}

export interface BuiltInTool {
  name: string;
  description: string;
  input_schema?: Record<string, any>;
}

export interface BuiltInToolsResponse {
  tools: BuiltInTool[];
  error?: string;
}

async function fetchBuiltInToolsWithError(): Promise<BuiltInToolsResponse> {
  const result = await fetchBuiltInTools();
  if (result.error) {
    throw new FetchError(
      i18n.t("common.fetchError", {
        defaultValue: "An error occurred while fetching the data.",
      }),
      0,
      { error: result.error }
    );
  }
  return result;
}

/**
 * Fetch built-in tools from the tools-service MCP server.
 * These are the tools available from the local tools-service.
 *
 * The response is translated server-side based on the app's selected
 * language, so the language is sent as a header and included in the SWR
 * key to force a refetch whenever it changes.
 */
export function useBuiltInTools() {
  const { i18n } = useTranslation();
  const { data, error, isLoading, mutate } = useSWR<BuiltInToolsResponse>(
    [toolsEndpoints.listBuiltInTools.browserPath, i18n.language],
    fetchBuiltInToolsWithError,
    {
      revalidateOnFocus: false,
      dedupingInterval: 30000, // 30 seconds
    }
  );

  return {
    tools: data?.tools ?? [],
    isLoading,
    error: error || data?.error,
    refresh: mutate,
  };
}

const HEALTH_ENDPOINT = toolsEndpoints.codeInterpreterHealth.browserPath;

const STATUS_ENDPOINT = toolsEndpoints.codeInterpreter.browserPath;

export function useCodeInterpreter() {
  const {
    data: healthData,
    error: healthError,
    isLoading: isHealthLoading,
    mutate: refetchHealth,
  } = useSWR(HEALTH_ENDPOINT, () => fetchCodeInterpreterHealth(), {
    refreshInterval: 30000,
  });

  const {
    data: statusData,
    error: statusError,
    isLoading: isStatusLoading,
    mutate: refetchStatus,
  } = useSWR(STATUS_ENDPOINT, () => fetchCodeInterpreterStatus());

  function refetch() {
    refetchHealth();
    refetchStatus();
  }

  return {
    isHealthy: healthData?.healthy ?? false,
    isEnabled: statusData?.enabled ?? false,
    isLoading: isHealthLoading || isStatusLoading,
    error: healthError || statusError,
    refetch,
  };
}

/**
 * Fetches MCP (Model Context Protocol) servers configuration.
 *
 * MCP servers provide additional tools and capabilities to agents through
 * the Model Context Protocol.
 *
 * @returns Object containing:
 *   - mcpData: MCPServersResponse data or null if not loaded
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Any error that occurred during fetch
 *   - mutateMcpServers: Function to manually revalidate the data
 *
 * @example
 * const { mcpData, isLoading } = useMcpServers();
 * if (isLoading) return <Spinner />;
 * return <MCPServersList servers={mcpData} />;
 */
export function useMcpServers() {
  const { i18n } = useTranslation();
  const {
    data: mcpData,
    error,
    isLoading: isMcpLoading,
    mutate: mutateMcpServers,
  } = useSWR<MCPServersResponse>(
    [toolsEndpoints.adminServers.browserPath, i18n.language],
    () => fetchMcpServers()
  );

  return {
    mcpData: mcpData ?? null,
    isLoading: isMcpLoading,
    error,
    mutateMcpServers,
  };
}

/**
 * Fetch MCP servers for non-admin UIs (e.g. agent editor).
 *
 * This endpoint is available to all authenticated users so basic users can
 * attach MCP actions to assistants.
 */
export function useMcpServersForAgentEditor() {
  const {
    data: mcpData,
    error,
    isLoading: isMcpLoading,
    mutate: mutateMcpServers,
  } = useSWR<MCPServersResponse>(
    toolsEndpoints.fetchMcpServersForAgent.browserPath,
    () => fetchMcpServersForAgent()
  );

  return {
    mcpData: mcpData ?? null,
    isLoading: isMcpLoading,
    error,
    mutateMcpServers,
  };
}

/**
 * Fetches OpenAPI tools configuration.
 *
 * OpenAPI tools provide custom actions and integrations to agents through
 * OpenAPI specifications.
 *
 * @returns Object containing:
 *   - openApiTools: ToolSnapshot[] data or null if not loaded
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Any error that occurred during fetch
 *   - mutateOpenApiTools: Function to manually revalidate the data
 *
 * @example
 * const { openApiTools, isLoading } = useOpenApiTools();
 * if (isLoading) return <Spinner />;
 * return <OpenApiToolsList tools={openApiTools} />;
 */
export function useOpenApiTools() {
  const {
    data: openApiTools,
    error,
    isLoading: isOpenApiLoading,
    mutate: mutateOpenApiTools,
  } = useSWR<ToolSnapshot[]>(toolsEndpoints.openapiTools.browserPath, () =>
    fetchOpenApiTools()
  );

  return {
    openApiTools: openApiTools ?? null,
    isLoading: isOpenApiLoading,
    error,
    mutateOpenApiTools,
  };
}

/**
 * Return type for the useServerTools hook
 */
interface UseServerToolsReturn {
  /** Array of tools available for the MCP server, formatted for UI display */
  tools: MCPTool[];

  /** Loading state - true when fetching tools from the API */
  isLoading: boolean;

  /** Error object if the fetch failed, undefined otherwise */
  error: Error | undefined;

  /** SWR mutate function for manually revalidating or updating the tools cache */
  mutate: KeyedMutator<ToolSnapshot[]>;
}

/**
 * useServerTools
 *
 * A custom hook for lazily loading and managing tools for a specific MCP server.
 * This hook only fetches tools when the server is expanded, reducing unnecessary
 * API calls and improving performance.
 *
 * @param server - The MCP server object containing server metadata (id, url, name)
 * @param isExpanded - Boolean flag indicating whether the server card is expanded.
 *                     Tools are only fetched when this is true.
 *
 * @returns An object containing:
 *   - tools: Array of MCPTool objects formatted for UI display
 *   - isLoading: Boolean indicating if tools are currently being fetched
 *   - error: Error object if fetch failed
 *   - mutate: Function to manually revalidate or update the tools cache
 *
 * @example
 * ```tsx
 * function ServerCard({ server }) {
 *   const [isExpanded, setIsExpanded] = useState(false);
 *   const { tools, isLoading, error, mutate } = useServerTools(server, isExpanded);
 *
 *   if (isLoading) return <div>Loading tools...</div>;
 *   if (error) return <div>Failed to load tools</div>;
 *
 *   return (
 *     <div>
 *       <button onClick={() => setIsExpanded(!isExpanded)}>
 *         {isExpanded ? 'Collapse' : 'Expand'}
 *       </button>
 *       {isExpanded && tools.map(tool => (
 *         <ToolItem key={tool.id} {...tool} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 *
 * @remarks
 * - Uses SWR for caching and automatic revalidation
 * - Automatically converts ToolSnapshot[] from API to MCPTool[] for UI
 * - Revalidation on focus and reconnect are disabled to reduce API calls
 * - The hook will not fetch if isExpanded is false (lazy loading)
 */
export function useServerTools(
  server: MCPServer,
  isExpanded: boolean
): UseServerToolsReturn {
  const shouldFetch = isExpanded;

  const {
    data: toolsData,
    isLoading,
    error,
    mutate,
  } = useSWR<ToolSnapshot[]>(
    shouldFetch
      ? toolsEndpoints.mcpStoredSnapshotsKey(server.id).browserPath
      : null,
    () => fetchMcpServerToolsSnapshots(server.id),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  // Convert ToolSnapshot[] to MCPTool[] format for UI consumption
  const tools: MCPTool[] = toolsData
    ? toolsData.map((tool) => ({
        id: tool.id.toString(),
        icon: getActionIcon(server.server_url, server.name),
        name: tool.display_name || tool.name,
        description: tool.description,
        isAvailable: true,
        isEnabled: tool.enabled,
        schema: tool.input_schema,
      }))
    : [];

  return {
    tools,
    isLoading,
    error,
    mutate,
  };
}
