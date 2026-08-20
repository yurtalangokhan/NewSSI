"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { MinimalUserSnapshot } from "@/lib/types";

export interface UseShareableUsersParams {
  includeApiKeys: boolean;
}

interface RawUsersResponse {
  users?: MinimalUserSnapshot[];
  items?: MinimalUserSnapshot[];
  accepted?: MinimalUserSnapshot[];
}

export default function useShareableUsers({
  includeApiKeys,
}: UseShareableUsersParams) {
  const { data: rawData, error, mutate, isLoading } = useSWR<
    MinimalUserSnapshot[] | RawUsersResponse
  >(
    `/api/users?include_api_keys=${includeApiKeys}`,
    errorHandlingFetcher
  );

  const data = useMemo<MinimalUserSnapshot[] | undefined>(() => {
    if (!rawData) return undefined;
    if (Array.isArray(rawData)) return rawData;
    if (Array.isArray(rawData.users)) return rawData.users;
    if (Array.isArray(rawData.items)) return rawData.items;
    if (Array.isArray(rawData.accepted)) return rawData.accepted;
    return [];
  }, [rawData]);

  return {
    data,
    isLoading,
    error,
    refreshShareableUsers: mutate,
  };
}