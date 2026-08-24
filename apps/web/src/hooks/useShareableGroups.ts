"use client";

import { useContext, useMemo } from "react";
import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SettingsContext } from "@/providers/SettingsProvider";

export interface MinimalUserGroupSnapshot {
  id: number;
  name: string;
}

// TODO (@raunakab):
// Refactor this hook to live inside of a special `ee` directory.

interface RawGroupsResponse {
  groups?: MinimalUserGroupSnapshot[];
  items?: MinimalUserGroupSnapshot[];
}

export default function useShareableGroups() {
  const combinedSettings = useContext(SettingsContext);
  const isPaidEnterpriseFeaturesEnabled =
    combinedSettings && combinedSettings.enterpriseSettings !== null;

  const { data: rawData, error, mutate, isLoading } = useSWR<
    MinimalUserGroupSnapshot[] | RawGroupsResponse
  >(
    isPaidEnterpriseFeaturesEnabled ? "/api/manage/user-groups/minimal" : null,
    errorHandlingFetcher
  );

  const data = useMemo<MinimalUserGroupSnapshot[] | undefined>(() => {
    if (!isPaidEnterpriseFeaturesEnabled) return [];
    if (!rawData) return undefined;
    if (Array.isArray(rawData)) return rawData;
    if (Array.isArray(rawData.groups)) return rawData.groups;
    if (Array.isArray(rawData.items)) return rawData.items;
    return [];
  }, [isPaidEnterpriseFeaturesEnabled, rawData]);

  if (!isPaidEnterpriseFeaturesEnabled) {
    return {
      data: [],
      isLoading: false,
      error: undefined,
      refreshShareableGroups: () => {},
    };
  }

  return {
    data,
    isLoading,
    error,
    refreshShareableGroups: mutate,
  };
}