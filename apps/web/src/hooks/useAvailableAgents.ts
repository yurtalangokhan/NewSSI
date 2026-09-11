import { authenticatedFetch } from "@/lib/fetcher";
/**
 * Hook to fetch agents available for composition.
 * Filters agents based on schema compatibility.
 *
 * Uses POST for cleaner API design and easier payload handling.
 */

import useSWR from "swr";
import { useCallback } from "react";

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
      const response = await authenticatedFetch(
        "/api/agent-definitions/available-for-composition",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            schema: schema || undefined,
            exclude_ids: excludeIds.length > 0 ? excludeIds : undefined,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(
          `Failed to fetch available agents: ${response.statusText}`
        );
      }

      return response.json();
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
