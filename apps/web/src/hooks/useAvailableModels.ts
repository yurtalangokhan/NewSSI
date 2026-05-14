"use client";

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { LLMProviderDescriptor } from "@/interfaces/llm";

export function useAvailableModels(): {
  llmProviders: LLMProviderDescriptor[] | undefined;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
} {
  const { data, error, mutate } = useSWR<LLMProviderDescriptor[]>(
    "/api/admin/providers/available-models",
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  return {
    llmProviders: data,
    isLoading: !error && !data,
    error,
    refetch: () => {
      void mutate();
    },
  };
}
