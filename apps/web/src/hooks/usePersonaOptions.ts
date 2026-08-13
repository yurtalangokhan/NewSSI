"use client";

import useSWR from "swr";

import { errorHandlingFetcher } from "@/lib/fetcher";

export interface PersonaOption {
  id: number;
  name: string;
  description: string;
}

export function usePersonaOptions() {
  const { data, error, isLoading, mutate } = useSWR<PersonaOption[]>(
    "/api/persona/options",
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60_000,
    }
  );

  return {
    personas: data ?? [],
    error,
    isLoading,
    refresh: mutate,
  };
}
