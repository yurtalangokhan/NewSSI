"use client";

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  AllProvidersResponse,
  ApiKeyProvider,
  WellKnownLangChainProvider,
} from "@/interfaces/llm";

export function useAllProviders() {
  const { data, error, isLoading, mutate } = useSWR<AllProvidersResponse>(
    "/api/admin/providers",
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  return {
    providers: data,
    isLoading,
    error,
    refetch: mutate,
  };
}

export function useApiKeyProviders() {
  const { data, error, isLoading, mutate } = useSWR<ApiKeyProvider[]>(
    "/api/admin/user-providers",
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  return {
    apiKeyProviders: data ?? [],
    isLoading,
    error,
    refetch: mutate,
  };
}

export function useWellKnownLangChainProviders() {
  const { data, error, isLoading, mutate } = useSWR<WellKnownLangChainProvider[]>(
    "/api/admin/providers/well-known",
    errorHandlingFetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );
  return {
    wellKnownProviders: data ?? [],
    isLoading,
    error,
    mutate,
  };
}
