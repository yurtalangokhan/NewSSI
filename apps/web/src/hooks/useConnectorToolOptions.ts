import useSWR from "swr";

import { errorHandlingFetcher } from "@/lib/fetcher";

export const CONNECTOR_OPERATIONS = ["list_resources", "read"] as const;
export type ConnectorOperation = (typeof CONNECTOR_OPERATIONS)[number];

export interface ConnectorToolOption {
  id: string;
  name: string;
  connector_type: string;
  operations: string[];
  unavailable_reason: string | null;
}

export interface ConnectorBinding {
  datasource_id: string;
  operations: string[];
}

export default function useConnectorToolOptions() {
  const { data, error, isLoading } = useSWR<ConnectorToolOption[]>(
    "/api/agent/datasources/tool-options",
    errorHandlingFetcher
  );

  return { options: data, error, isLoading };
}
