"use client";

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  AllProvidersResponse,
  ApiKeyProvider,
  UrlBasedProvider,
  WellKnownLangChainProvider,
} from "@/interfaces/llm";

type ProvidersApiResponse = AllProvidersResponse;

export function useAllProviders() {
  const { data, error, isLoading, mutate } = useSWR<ProvidersApiResponse>(
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

export function useUrlProviders() {
  const { data, error, isLoading, mutate } = useSWR<ProvidersApiResponse>(
    "/api/admin/providers",
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  return {
    data: data?.url_providers ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useApiKeyProviders() {
  const { data, error, isLoading, mutate } = useSWR<ApiKeyProvider[]>(
    "/api/admin/user-providers",
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  return {
    data: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useWellKnownLangChainProviders() {
  const { data, error, isLoading, mutate } = useSWR<WellKnownLangChainProvider[]>(
    "/api/admin/providers/well-known",
    errorHandlingFetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );
  return {
    data: data ?? [],
    isLoading,
    error,
    mutate,
  };
}
