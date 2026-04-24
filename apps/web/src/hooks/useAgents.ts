"use client";

import useSWR from "swr";
import { useState, useEffect, useMemo, useCallback } from "react";
import {
  AgentId,
  DynamicAgentDefinition,
  MinimalPersonaSnapshot,
  FullPersona,
} from "@/app/admin/agents/interfaces";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { pinAgents } from "@/lib/agents";
import { useUser } from "@/providers/UserProvider";
import { useSearchParams } from "next/navigation";
import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import useChatSessions from "./useChatSessions";
import { ToolSnapshot } from "@/lib/tools/interfaces";
import { MinimalUserSnapshot } from "@/lib/types";

export function agentIdsMatch(
  left: AgentId | MinimalPersonaSnapshot | null | undefined,
  right: AgentId | MinimalPersonaSnapshot | null | undefined
) {
  if (left === null || left === undefined || right === null || right === undefined) {
    return false;
  }

  const leftValue = typeof left === "object" ? left.external_id ?? left.id : left;
  const rightValue = typeof right === "object" ? right.external_id ?? right.id : right;

  return String(leftValue) === String(rightValue);
}

function definitionIdToSyntheticId(definitionId: string): number {
  let hash = 0;
  for (let index = 0; index < definitionId.length; index += 1) {
    hash = (hash * 31 + definitionId.charCodeAt(index)) | 0;
  }

  return -(Math.abs(hash) || 1);
}

function sortAgents(left: MinimalPersonaSnapshot, right: MinimalPersonaSnapshot) {
  if (typeof left.id === "number" && typeof right.id === "number") {
    return right.id - left.id;
  }
  return left.name.localeCompare(right.name);
}

function buildDynamicAgentSnapshot(
  definition: DynamicAgentDefinition,
  tools: ToolSnapshot[],
  owner: MinimalUserSnapshot | null = null
): MinimalPersonaSnapshot {
  const mappedTools = tools.filter(
    (tool) =>
      definition.mcp_tools.includes(tool.name) ||
      (tool.in_code_tool_id && definition.mcp_tools.includes(tool.in_code_tool_id))
  );

  return {
    id: definitionIdToSyntheticId(definition.id),
    external_id: definition.id,
    is_dynamic: true,
    graph_schema: definition.graph_schema,
    mcp_tools: definition.mcp_tools,
    name: definition.name,
    description: definition.description ?? `${definition.graph_schema} dynamic agent`,
    tools: mappedTools,
    starter_messages: null,
    document_sets: [],
    hierarchy_node_count: 0,
    attached_document_count: 0,
    knowledge_sources: [],
    llm_model_version_override: definition.model ?? undefined,
    llm_model_provider_override: undefined,
    is_public: true,
    is_visible: definition.is_active,
    display_priority: null,
    featured: false,
    builtin_persona: false,
    owner,
    labels: [],
    icon_name: "bot",
  };
}

function buildDynamicAgentFullPersona(
  definition: DynamicAgentDefinition,
  tools: ToolSnapshot[]
): FullPersona {
  const ragConfig = definition.rag_config ?? {
    document_processing: [],
    knowledge_graph: [],
  };

  return {
    ...buildDynamicAgentSnapshot(definition, tools),
    user_file_ids: [],
    users: [],
    groups: [],
    hierarchy_nodes: [],
    attached_documents: [],
    system_prompt: definition.system_prompt,
    replace_base_system_prompt: true,
    task_prompt: definition.pipeline_prompt ?? definition.supervisor_prompt ?? definition.reflection_prompt,
    datetime_aware: false,
    base_agent: "dynamic-agent",
    mcp_tools: definition.mcp_tools,
    rag_config: ragConfig,
    search_start_date: null,
  };
}

/**
 * Fetches all agents (personas) available to the current user.
 *
 * Returns minimal agent snapshots containing basic information like name, description,
 * tools, and display settings. Use this for listing agents in UI components like
 * sidebars, dropdowns, or agent selection interfaces.
 *
 * For full agent details including user_file_ids, groups, and advanced settings,
 * use `useAgent(personaId)` instead.
 *
 * @returns Object containing:
 *   - agents: Array of MinimalPersonaSnapshot objects (empty array while loading)
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Any error that occurred during fetch
 *   - refresh: Function to manually revalidate the data
 *
 * @example
 * const { agents, isLoading } = useAgents();
 * if (isLoading) return <Spinner />;
 * return <AgentList agents={agents} />;
 */
export function useAgents() {
  const { user } = useUser();
  const { data, error, mutate } = useSWR<MinimalPersonaSnapshot[]>(
    "/api/persona",
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const {
    data: dynamicDefinitions,
    error: dynamicError,
    mutate: mutateDynamicDefinitions,
  } = useSWR<DynamicAgentDefinition[]>(
    "/api/agent-definitions?active_only=true",
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const { data: availableTools } = useSWR<ToolSnapshot[]>(
    "/api/tool",
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  const agents = useMemo(() => {
    const personaAgents = data ?? [];
    const toolCatalog = availableTools ?? [];
    const dynamicOwner: MinimalUserSnapshot = {
      id: user?.id ?? "dev@local.dev",
      email: user?.email ?? "dev@local.dev",
    };
    const dynamicAgents = (dynamicDefinitions ?? []).map((definition) =>
      buildDynamicAgentSnapshot(definition, toolCatalog, dynamicOwner)
    );

    return [...personaAgents, ...dynamicAgents].sort(sortAgents);
  }, [data, dynamicDefinitions, availableTools, user?.email, user?.id]);

  return {
    agents,
    isLoading:
      (!error && !data) ||
      (!dynamicError && !dynamicDefinitions) ||
      !availableTools,
    error: error ?? dynamicError,
    refresh: async () => {
      await Promise.all([mutate(), mutateDynamicDefinitions()]);
    },
  };
}

/**
 * Fetches a single agent (persona) by ID with full details.
 *
 * Returns complete agent information including user_file_ids, groups, system prompts,
 * and all configuration settings. Use this when you need detailed agent data for
 * editing, configuration, or displaying full agent details.
 *
 * For listing multiple agents with basic information, use `useAgents()` instead.
 *
 * @param agentId - The ID of the agent to fetch, or null to skip fetching
 * @returns Object containing:
 *   - agent: FullPersona object with complete agent details, or null if not loaded/not found
 *   - isLoading: Boolean indicating if data is being fetched (false when personaId is null)
 *   - error: Any error that occurred during fetch
 *   - refresh: Function to manually revalidate the data
 *
 * @example
 * const { agent, isLoading } = useAgent(selectedAgentId);
 * if (isLoading) return <Spinner />;
 * if (!agent) return <NotFound />;
 * return <AgentEditor agent={agent} />;
 */
export function useAgent(agentId: AgentId | null) {
  const { data: personaData, error: personaError, isLoading: isPersonaLoading, mutate: mutatePersona } = useSWR<FullPersona>(
    agentId && typeof agentId === "number" ? `/api/persona/${agentId}` : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const { data: dynamicData, error: dynamicError, isLoading: isDynamicLoading, mutate: mutateDynamic } = useSWR<DynamicAgentDefinition>(
    agentId && typeof agentId === "string" ? `/api/agent-definitions/${agentId}` : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const { data: availableTools } = useSWR<ToolSnapshot[]>("/api/tool", errorHandlingFetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const agent = useMemo(() => {
    if (personaData) {
      return personaData;
    }
    if (dynamicData) {
      return buildDynamicAgentFullPersona(dynamicData, availableTools ?? []);
    }
    return null;
  }, [personaData, dynamicData, availableTools]);

  return {
    agent,
    isLoading: isPersonaLoading || isDynamicLoading,
    error: personaError ?? dynamicError,
    refresh: async () => {
      await Promise.all([mutatePersona(), mutateDynamic()]);
    },
  };
}

/**
 * Hook that combines useAgents and usePinnedAgents to return full agent objects
 * with local state for optimistic drag-and-drop updates.
 */
export function usePinnedAgents() {
  const { user, refreshUser } = useUser();
  const { agents, isLoading: isLoadingAgents } = useAgents();

  // Local state for optimistic updates during drag-and-drop
  const [localPinnedAgents, setLocalPinnedAgents] = useState<
    MinimalPersonaSnapshot[]
  >([]);

  // Derive pinned agents from server data
  const serverPinnedAgents = useMemo(() => {
    if (agents.length === 0) return [];

    // If pinned_assistants is null/undefined (never set), show featured personas
    // If it's an empty array (user explicitly unpinned all), show nothing
    const pinnedIds = user?.preferences.pinned_assistants;
    if (pinnedIds === null || pinnedIds === undefined) {
      return agents.filter((agent) => agent.featured && agent.id !== 0);
    }

    return pinnedIds
      .map((id) => agents.find((agent) => agentIdsMatch(agent, id)))
      .filter((agent): agent is MinimalPersonaSnapshot => !!agent);
  }, [agents, user?.preferences.pinned_assistants]);

  // Sync server data → local state when server data changes
  // Only sync when agents have loaded (to avoid syncing empty during initial load)
  useEffect(() => {
    if (agents.length > 0) {
      setLocalPinnedAgents(serverPinnedAgents);
    }
  }, [serverPinnedAgents, agents.length]);

  // Toggle pin status - updates local state AND persists to server
  const togglePinnedAgent = useCallback(
    async (agent: MinimalPersonaSnapshot, shouldPin: boolean) => {
      const newPinned = shouldPin
        ? [...localPinnedAgents, agent]
        : localPinnedAgents.filter((a) => a.id !== agent.id);

      // Optimistic update
      setLocalPinnedAgents(newPinned);

      // Persist to server
      await pinAgents(newPinned.map((a) => a.id));
      refreshUser(); // Refresh user to sync pinned_assistants
    },
    [localPinnedAgents, refreshUser]
  );

  // Update pinned agents order (for drag-and-drop) - updates AND persists
  const updatePinnedAgents = useCallback(
    async (newPinnedAgents: MinimalPersonaSnapshot[]) => {
      // Optimistic update
      setLocalPinnedAgents(newPinnedAgents);

      // Persist to server
      await pinAgents(newPinnedAgents.map((a) => a.id));
      refreshUser();
    },
    [refreshUser]
  );

  return {
    pinnedAgents: localPinnedAgents,
    togglePinnedAgent,
    updatePinnedAgents, // Use this instead of setPinnedAgents for drag-and-drop
    isLoading: isLoadingAgents,
  };
}

/**
 * Hook to determine the currently active agent based on:
 * 1. URL param `agentId`
 * 2. Chat session's `persona_id`
 * 3. Falls back to null if neither is present
 */
export function useCurrentAgent(): MinimalPersonaSnapshot | null {
  const { agents } = useAgents();
  const searchParams = useSearchParams();

  const agentIdRaw = searchParams?.get(SEARCH_PARAM_NAMES.PERSONA_ID);
  const { currentChatSession } = useChatSessions();

  const currentAgent = useMemo(() => {
    if (agents.length === 0) return null;

    // Priority: URL param > chat session persona > null
    const agentId = agentIdRaw ?? currentChatSession?.persona_id;

    if (!agentId) return null;

    return agents.find((a) => agentIdsMatch(a, agentId)) ?? null;
  }, [agents, agentIdRaw, currentChatSession?.persona_id]);

  return currentAgent;
}
