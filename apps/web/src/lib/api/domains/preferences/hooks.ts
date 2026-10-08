"use client";
import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";

import { ValidSources } from "@/lib/types";
import { useEffect } from "react";
import { useMemo } from "react";
import { useState } from "react";
import { SourceMetadata } from "@/lib/search/interfaces";
import { getSourceMetadataForSources } from "@/lib/sources";
import useSWR from "swr";
import { UserSpecificAgentPreference } from "@/lib/types";
import { UserSpecificAgentPreferences } from "@/lib/types";
import { useCallback } from "react";
import { fetchAssistantPreferencesWithError } from "./api";
import { updateAgentPreferences as domainUpdateAgentPreferences } from "./api";

import { InputPrompt } from "@/lib/api/domains/chat/types";
import { fetchInputPrompts } from "./api";
import { useUser } from "@/providers/UserProvider";

const EMPTY_PROMPT_SHORTCUTS: InputPrompt[] = [];

function getConfiguredSources(
  availableSources: ValidSources[]
): Array<SourceMetadata & { originalName: string; uniqueKey: string }> {
  const allSources = getSourceMetadataForSources(availableSources);

  const seenSources = new Set<string>();
  const configuredSources: Array<
    SourceMetadata & { originalName: string; uniqueKey: string }
  > = [];

  availableSources.forEach((sourceName) => {
    // Handle federated connectors by removing the federated_ prefix
    const cleanName = sourceName.replace("federated_", "");
    // Skip if we've already seen this source type
    if (seenSources.has(cleanName)) return;
    seenSources.add(cleanName);
    const source = allSources.find(
      (source) => source.internalName === cleanName
    );
    if (source) {
      configuredSources.push({
        ...source,
        originalName: sourceName,
        uniqueKey: cleanName,
      });
    }
  });
  return configuredSources;
}

interface UseSourcePreferencesProps {
  availableSources: ValidSources[];
  selectedSources: SourceMetadata[];
  setSelectedSources: (sources: SourceMetadata[]) => void;
}

interface SourcePreferencesSnapshot {
  sourcePreferences: Record<string, boolean>; // uniqueKey -> enabled status
}

const LS_SELECTED_INTERNAL_SEARCH_SOURCES_KEY = "selectedInternalSearchSources";

export function useSourcePreferences({
  availableSources,
  selectedSources,
  setSelectedSources,
}: UseSourcePreferencesProps) {
  const [sourcesInitialized, setSourcesInitialized] = useState(false);

  const configuredSources = useMemo(
    () => getConfiguredSources(availableSources),
    [availableSources]
  );

  // Load saved source preferences from localStorage
  const loadSavedSourcePreferences = (): SourcePreferencesSnapshot | null => {
    if (typeof window === "undefined") return null;
    const saved = localStorage.getItem(LS_SELECTED_INTERNAL_SEARCH_SOURCES_KEY);
    if (!saved) return null;
    try {
      const res = JSON.parse(saved);

      // Validate the snapshot structure
      if (
        typeof res !== "object" ||
        res === null ||
        typeof res.sourcePreferences !== "object" ||
        res.sourcePreferences === null ||
        Array.isArray(res.sourcePreferences)
      ) {
        return null;
      }

      // Validate that all values in sourcePreferences are booleans
      for (const value of Object.values(res.sourcePreferences)) {
        if (typeof value !== "boolean") {
          return null;
        }
      }

      return res as SourcePreferencesSnapshot;
    } catch {
      return null;
    }
  };

  const persistSourcePreferencesState = (
    enabledSources: SourceMetadata[],
    allKnownSources: SourceMetadata[]
  ) => {
    if (typeof window === "undefined") return;

    const enabledKeys = new Set(enabledSources.map((s) => s.uniqueKey));

    const snapshot: SourcePreferencesSnapshot = {
      sourcePreferences: Object.fromEntries(
        allKnownSources
          .filter((src) => src.uniqueKey !== undefined)
          .map((src) => [src.uniqueKey, enabledKeys.has(src.uniqueKey)])
      ),
    };

    localStorage.setItem(
      LS_SELECTED_INTERNAL_SEARCH_SOURCES_KEY,
      JSON.stringify(snapshot)
    );
  };

  // Initialize sources - load from localStorage or enable all by default
  useEffect(() => {
    if (!sourcesInitialized && availableSources.length > 0) {
      const savedSources = loadSavedSourcePreferences();

      if (savedSources !== null) {
        // Filter out saved sources that no longer exist
        const { sourcePreferences } = savedSources;

        // Helper to check if there is a preference for a key
        const hasPref = (key: string) =>
          Object.prototype.hasOwnProperty.call(sourcePreferences, key);

        // Get sources with no preference
        const newSources = configuredSources.filter((source) => {
          return !hasPref(source.uniqueKey);
        });

        const enabledSources = configuredSources.filter((source) => {
          return (
            hasPref(source.uniqueKey) && sourcePreferences[source.uniqueKey]
          );
        });

        // Merge valid saved sources with new sources (enable new sources by default)
        const mergedSources = [...enabledSources, ...newSources];
        setSelectedSources(mergedSources);

        // Persist the merged state
        persistSourcePreferencesState(mergedSources, configuredSources);
      } else {
        // First time user or invalid data - enable all sources by default
        setSelectedSources(configuredSources);
        persistSourcePreferencesState(configuredSources, configuredSources);
      }
      setSourcesInitialized(true);
    }
  }, [
    availableSources,
    configuredSources,
    sourcesInitialized,
    setSelectedSources,
  ]);

  const enableSources = (sources: SourceMetadata[]) => {
    setSelectedSources([...sources]);
    persistSourcePreferencesState(sources, configuredSources);
  };

  const enableAllSources = () => {
    enableSources(configuredSources);
  };

  const disableAllSources = () => {
    setSelectedSources([]);
    persistSourcePreferencesState([], configuredSources);
  };

  const toggleSource = (sourceUniqueKey: string) => {
    const configuredSource = configuredSources.find(
      (s) => s.uniqueKey === sourceUniqueKey
    );
    if (!configuredSource) return;

    const isCurrentlySelected = selectedSources.some(
      (s) => s.uniqueKey === configuredSource.uniqueKey
    );

    let newSources: SourceMetadata[];
    if (isCurrentlySelected) {
      newSources = selectedSources.filter(
        (s) => s.uniqueKey !== configuredSource.uniqueKey
      );
    } else {
      newSources = [...selectedSources, configuredSource];
    }

    setSelectedSources(newSources);
    persistSourcePreferencesState(newSources, configuredSources);
  };

  const isSourceEnabled = (sourceUniqueKey: string) => {
    const configuredSource = configuredSources.find(
      (s) => s.uniqueKey === sourceUniqueKey
    );
    if (!configuredSource) return false;
    return selectedSources.some(
      (s: SourceMetadata) => s.uniqueKey === configuredSource.uniqueKey
    );
  };

  return {
    sourcesInitialized,
    enableSources,
    enableAllSources,
    disableAllSources,
    toggleSource,
    isSourceEnabled,
  };
}

/**
 * Hook for managing user-specific agent preferences using SWR.
 * Provides automatic caching, deduplication, and revalidation.
 */
export function useAgentPreferences() {
  const { data, mutate } = useSWR<UserSpecificAgentPreferences>(
    preferencesEndpoints.getAssistantPreferences().browserPath,
    () => fetchAssistantPreferencesWithError(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  const setSpecificAgentPreferences = useCallback(
    async (
      agentId: number,
      newAgentPreference: UserSpecificAgentPreference
    ) => {
      // Optimistic update
      mutate(
        {
          ...data,
          [agentId]: newAgentPreference,
        },
        false
      );

      try {
        await domainUpdateAgentPreferences(agentId, newAgentPreference);
      } catch (error) {
        console.error("Error updating agent preferences:", error);
      }

      // Revalidate after update
      mutate();
    },
    [data, mutate]
  );

  return {
    agentPreferences: data ?? null,
    setSpecificAgentPreferences,
  };
}

export function usePromptShortcuts() {
  const { hasPermission } = useUser();
  const canReadSettings = hasPermission("settings:read");
  const { data, error, isLoading, mutate } = useSWR<InputPrompt[]>(
    canReadSettings ? preferencesEndpoints.getInputPrompts.browserPath : null,
    () => fetchInputPrompts<InputPrompt[]>()
  );

  const promptShortcuts = canReadSettings
    ? data ?? EMPTY_PROMPT_SHORTCUTS
    : EMPTY_PROMPT_SHORTCUTS;
  const userPromptShortcuts = promptShortcuts.filter((p) => !p.is_public);
  const activePromptShortcuts = promptShortcuts.filter((p) => p.active);

  return {
    promptShortcuts,
    userPromptShortcuts,
    activePromptShortcuts,
    isLoading: canReadSettings && isLoading,
    error,
    refresh: canReadSettings ? mutate : async () => undefined,
  };
}
