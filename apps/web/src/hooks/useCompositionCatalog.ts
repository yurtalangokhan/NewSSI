"use client";

import useSWR from "swr";
import { useMemo } from "react";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { COMPOSITION_CATALOG_API_PATH } from "@/lib/agents/apiPaths";

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
    COMPOSITION_CATALOG_API_PATH,
    errorHandlingFetcher,
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
