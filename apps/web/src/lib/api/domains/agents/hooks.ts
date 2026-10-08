"use client";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";

import useSWR from "swr";
import { useSWRConfig } from "swr";
import type { PersonaLabel } from "@/lib/api/domains/agents/types";
import { createPersonaLabel } from "@/lib/api/domains/agents/api";
import { deletePersonaLabel } from "@/lib/api/domains/agents/api";
import { fetchPersonaLabelsForSWR } from "@/lib/api/domains/agents/api";
import { updatePersonaLabel } from "@/lib/api/domains/agents/api";

import { fetchAdminPersonas } from "@/lib/api/domains/agents/api";
import { fetchPersonas } from "@/lib/api/domains/agents/api";
import { Persona } from "@/lib/api/domains/agents/types";
import { useMemo } from "react";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { AgentId } from "@/lib/api/domains/agents/types";
import { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import { FullPersona } from "@/lib/api/domains/agents/types";
import { fetchAgentCatalog } from "@/lib/api/domains/agents/api";
import { fetchAgentDetail } from "@/lib/api/domains/agents/api";

import { useUser } from "@/providers/UserProvider";
import { useChatSessions } from "@/lib/api/domains/chat/hooks";
import useAppFocus from "@/hooks/useAppFocus";
import { filterChatReadyAgents } from "@/lib/flows/flowAgent";
import { isFlowChatReady } from "@/lib/flows/flowAgent";
import { fetchAvailableForComposition } from "@/lib/api/domains/agents/api";
import { fetchCompositionCatalog } from "@/lib/api/domains/agents/api";

import { fetchPersonaOptions } from "@/lib/api/domains/agents/api";
import { fetchFlowSource } from "@/lib/api/domains/agents/api";

export function useLabels() {
  const { mutate } = useSWRConfig();
  const { data: labels, error } = useSWR<PersonaLabel[]>(
    agentsEndpoints.personaLabels.browserPath,
    () => fetchPersonaLabelsForSWR<PersonaLabel[]>()
  );
  const refreshLabels = () => mutate(agentsEndpoints.personaLabels.browserPath);
  const createLabel = async (name: string): Promise<PersonaLabel | null> => {
    const response = await createPersonaLabel({ name });
    if (!response.ok) return null;
    const newLabel: PersonaLabel = await response.json();
    mutate(
      agentsEndpoints.personaLabels.browserPath,
      (current: PersonaLabel[] | undefined) => [...(current || []), newLabel],
      false
    );
    return newLabel;
  };
  const updateLabel = async (id: number, name: string) => {
    const response = await updatePersonaLabel(id, { label_name: name });
    if (response.ok)
      mutate(
        agentsEndpoints.personaLabels.browserPath,
        labels?.map((label) => (label.id === id ? { ...label, name } : label)),
        false
      );
    return response;
  };
  const deleteLabel = async (id: number) => {
    const response = await deletePersonaLabel(id);
    if (response.ok)
      mutate(
        agentsEndpoints.personaLabels.browserPath,
        labels?.filter((label) => label.id !== id),
        false
      );
    return response;
  };
  return {
    labels,
    error,
    refreshLabels,
    createLabel,
    updateLabel,
    deleteLabel,
  };
}

interface UseAdminPersonasOptions {
  includeDeleted?: boolean;
  getEditable?: boolean;
  includeDefault?: boolean;
  pageNum?: number;
  pageSize?: number;
}

interface PaginatedPersonasResponse {
  items: Persona[];
  total_items: number;
}

export const useAdminPersonas = (options?: UseAdminPersonasOptions) => {
  const {
    includeDeleted = false,
    getEditable = false,
    includeDefault = false,
    pageNum,
    pageSize,
  } = options || {};

  // If pageNum and pageSize are provided, use paginated endpoint.
  const usePagination = pageNum !== undefined && pageSize !== undefined;

  const fetcher = () => {
    if (usePagination) {
      return fetchAdminPersonas<PaginatedPersonasResponse>({
        include_deleted: includeDeleted,
        get_editable: getEditable,
        include_default: includeDefault,
        page_num: pageNum,
        page_size: pageSize,
      });
    }
    return fetchPersonas<Persona[]>({
      include_deleted: includeDeleted,
      get_editable: getEditable,
    });
  };

  const key = usePagination
    ? agentsEndpoints.adminPersonas({
        include_deleted: includeDeleted,
        get_editable: getEditable,
        include_default: includeDefault,
        page_num: pageNum,
        page_size: pageSize,
      }).browserPath
    : agentsEndpoints.personas({
        include_deleted: includeDeleted,
        get_editable: getEditable,
      }).browserPath;

  const { data, error, isLoading, mutate } = useSWR<
    Persona[] | PaginatedPersonasResponse
  >(key, fetcher);

  // Handle both paginated and non-paginated responses
  const personas = usePagination
    ? (data as PaginatedPersonasResponse)?.items || []
    : (data as Persona[]) || [];

  const totalItems = usePagination
    ? (data as PaginatedPersonasResponse)?.total_items || 0
    : personas.length;

  return {
    personas,
    totalItems,
    error,
    isLoading,
    refresh: mutate,
  };
};

export function agentIdsMatch(
  left: AgentId | MinimalPersonaSnapshot | null | undefined,
  right: AgentId | MinimalPersonaSnapshot | null | undefined
) {
  if (
    left === null ||
    left === undefined ||
    right === null ||
    right === undefined
  ) {
    return false;
  }

  const leftValue =
    typeof left === "object" ? left.external_id ?? left.id : left;
  const rightValue =
    typeof right === "object" ? right.external_id ?? right.id : right;

  return String(leftValue) === String(rightValue);
}

function sortAgents(
  left: MinimalPersonaSnapshot,
  right: MinimalPersonaSnapshot
) {
  if (typeof left.id === "number" && typeof right.id === "number") {
    return right.id - left.id;
  }
  return left.name.localeCompare(right.name);
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
  const { i18n } = useTranslation();
  const { data, error, mutate } = useSWR<MinimalPersonaSnapshot[]>(
    [agentsEndpoints.agentCatalog().browserPath, i18n.language],
    () => fetchAgentCatalog<MinimalPersonaSnapshot[]>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const agents = useMemo(() => {
    const personaAgents = data ?? [];
    return [...personaAgents].sort(sortAgents);
  }, [data]);

  // A flow with no published version has nothing to run — chat surfaces
  // (agent picker, sidebar/pinned, @mention) must never offer it. The
  // Flows tab lists every flow regardless, so it reads `agents` directly.
  const chatReadyAgents = useMemo(
    () => filterChatReadyAgents(agents),
    [agents]
  );

  return {
    agents,
    chatReadyAgents,
    isLoading: !error && !data,
    error,
    refresh: async () => {
      await mutate();
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
  const { i18n } = useTranslation();
  const {
    data: personaData,
    error: personaError,
    isLoading: isPersonaLoading,
    mutate: mutatePersona,
  } = useSWR<FullPersona>(
    agentId && typeof agentId === "number"
      ? [agentsEndpoints.getAgent(agentId).browserPath, i18n.language]
      : null,
    () =>
      agentId && typeof agentId === "number"
        ? fetchAgentDetail<FullPersona>(agentId)
        : Promise.resolve(null as unknown as FullPersona),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const agent = useMemo(() => {
    if (personaData) {
      return personaData;
    }
    return null;
  }, [personaData]);

  return {
    agent,
    isLoading: isPersonaLoading,
    error: personaError,
    refresh: async () => {
      await mutatePersona();
    },
  };
}

/**
 * Hook that combines useAgents and usePinnedAgents to return full agent objects
 * with local state for optimistic drag-and-drop updates.
 */
export function usePinnedAgents() {
  const { user, updateUserPinnedAssistants } = useUser();
  const { agents, isLoading: isLoadingAgents } = useAgents();

  // Derive pinned agents from user preferences and available agents
  const pinnedAgents = useMemo(() => {
    if (agents.length === 0) return [];

    // If pinned_assistants is null/undefined (never set), show featured personas
    // If it's an empty array (user explicitly unpinned all), show nothing
    const pinnedIds = user?.preferences?.pinned_assistants;
    if (pinnedIds === null || pinnedIds === undefined) {
      return agents.filter(
        (agent) => agent.featured && agent.id !== 0 && isFlowChatReady(agent)
      );
    }

    return pinnedIds
      .map((id) => agents.find((agent) => agentIdsMatch(agent, id)))
      .filter((agent): agent is MinimalPersonaSnapshot => !!agent)
      .filter(isFlowChatReady);
  }, [agents, user?.preferences?.pinned_assistants]);

  // Toggle pin status - updates UserProvider context optimistically AND persists to server
  const togglePinnedAgent = useCallback(
    async (agent: MinimalPersonaSnapshot, shouldPin: boolean) => {
      const currentPinnedIds =
        user?.preferences?.pinned_assistants ??
        agents.filter((a) => a.featured && a.id !== 0).map((a) => a.id);

      const newPinnedIds = shouldPin
        ? currentPinnedIds.some((id) => String(id) === String(agent.id))
          ? currentPinnedIds
          : [...currentPinnedIds, agent.id]
        : currentPinnedIds.filter((id) => String(id) !== String(agent.id));

      await updateUserPinnedAssistants(newPinnedIds);
    },
    [user?.preferences?.pinned_assistants, agents, updateUserPinnedAssistants]
  );

  // Update pinned agents order (for drag-and-drop) - updates AND persists
  const updatePinnedAgents = useCallback(
    async (newPinnedAgents: MinimalPersonaSnapshot[]) => {
      const newPinnedIds = newPinnedAgents.map((a) => a.id);
      await updateUserPinnedAssistants(newPinnedIds);
    },
    [updateUserPinnedAssistants]
  );

  return {
    pinnedAgents,
    togglePinnedAgent,
    updatePinnedAgents,
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
  const appFocus = useAppFocus();
  const agentIdRaw = appFocus.isAgent() ? appFocus.getId() : null;
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

interface AvailableAgent {
  id: string;
  name: string;
  graph_schema: string;
  depth: number;
  status: "active" | "inactive";
  preview: string;
}

interface UseAvailableAgentsOptions {
  schema?: string | null;
  excludeIds?: string[];
  enabled?: boolean;
}

export function useAvailableAgents(options: UseAvailableAgentsOptions = {}) {
  const { schema, excludeIds = [], enabled = true } = options;

  // Build cache key based on parameters
  const cacheKey = enabled ? JSON.stringify({ schema, excludeIds }) : null;

  const { data, error, isLoading, mutate } = useSWR<AvailableAgent[]>(
    cacheKey,
    async () => {
      return fetchAvailableForComposition({
        schema,
        excludeIds,
      }) as Promise<AvailableAgent[]>;
    },
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000, // Cache for 1 minute
    }
  );

  const refetch = useCallback(() => {
    mutate();
  }, [mutate]);

  return {
    agents: data ?? [],
    isLoading,
    error,
    refetch,
  };
}

export interface CompositionComponent {
  key: string;
  kind: string;
  description: string;
  required_settings: string[];
  settings_schema: Record<string, string>;
  required_nested: boolean;
  incompatible_with: string[];
  available: boolean;
  capabilities: string[];
}

interface CompositionCatalogResponse {
  components: CompositionComponent[];
  kinds: string[];
}

export function useCompositionCatalog() {
  const { data, error } = useSWR<CompositionCatalogResponse>(
    agentsEndpoints.getCompositionCatalog().browserPath,
    () => fetchCompositionCatalog<CompositionCatalogResponse>(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 300000,
    }
  );

  const graphStrategies = useMemo(
    () => (data?.components ?? []).filter((c) => c.kind === "graph_strategy"),
    [data]
  );

  const brains = useMemo(
    () => (data?.components ?? []).filter((c) => c.kind === "brain"),
    [data]
  );

  const perceptrons = useMemo(
    () => (data?.components ?? []).filter((c) => c.kind === "perceptron"),
    [data]
  );

  const runtimePolicies = useMemo(
    () => (data?.components ?? []).filter((c) => c.kind === "runtime_policy"),
    [data]
  );

  return {
    components: data?.components ?? [],
    graphStrategies,
    brains,
    perceptrons,
    runtimePolicies,
    kinds: data?.kinds ?? [],
    isLoading: !error && !data,
    error,
  };
}

export interface PersonaOption {
  id: number;
  name: string;
  description: string;
}

export function usePersonaOptions() {
  const { data, error, isLoading, mutate } = useSWR<PersonaOption[]>(
    agentsEndpoints.personaOptions.browserPath,
    () => fetchPersonaOptions(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60_000,
    }
  );

  // Assignment rows and permissions share the agent ID as their identity.
  const seenIds = new Set<number>();
  const personas = (data ?? []).filter((persona) => {
    if (seenIds.has(persona.id)) return false;
    seenIds.add(persona.id);
    return true;
  });

  return {
    personas,
    error,
    isLoading,
    refresh: mutate,
  };
}

export function usePublishedFlowSpec<T>(
  agent:
    | Pick<MinimalPersonaSnapshot, "graph_schema" | "agent_definition_id">
    | null
    | undefined
) {
  const isFlowAgent =
    agent?.graph_schema === "flow" && Boolean(agent.agent_definition_id);

  return useSWR<T>(
    isFlowAgent
      ? agentsEndpoints.flowPublished(agent!.agent_definition_id!).browserPath
      : null,
    () => fetchFlowSource<T>(agent!.agent_definition_id!, "published")
  );
}
