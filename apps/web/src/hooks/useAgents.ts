"use client";

import useSWR from "swr";
import { useState, useEffect, useMemo, useCallback } from "react";
import {
  AgentId,
  MinimalPersonaSnapshot,
  FullPersona,
} from "@/app/admin/agents/interfaces";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { pinAgents } from "@/lib/agents";
import {
  AGENT_CATALOG_API_PATH,
  buildAgentDetailApiPath,
} from "@/lib/agents/apiPaths";
import { useUser } from "@/providers/UserProvider";
import useChatSessions from "./useChatSessions";
import useAppFocus from "@/hooks/useAppFocus";

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

function sortAgents(left: MinimalPersonaSnapshot, right: MinimalPersonaSnapshot) {
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
  const { data, error, mutate } = useSWR<MinimalPersonaSnapshot[]>(
    AGENT_CATALOG_API_PATH,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );
  const agents = useMemo(() => {
    const personaAgents = data ?? [];
    return [...personaAgents].sort(sortAgents);
  }, [data]);

  return {
    agents,
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
  const { data: personaData, error: personaError, isLoading: isPersonaLoading, mutate: mutatePersona } = useSWR<FullPersona>(
    agentId && typeof agentId === "number"
      ? buildAgentDetailApiPath(agentId)
      : null,
    errorHandlingFetcher,
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
      return agents.filter((agent) => agent.featured && agent.id !== 0);
    }

    return pinnedIds
      .map((id) => agents.find((agent) => agentIdsMatch(agent, id)))
      .filter((agent): agent is MinimalPersonaSnapshot => !!agent);
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
