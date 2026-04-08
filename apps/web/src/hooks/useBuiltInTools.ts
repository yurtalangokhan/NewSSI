"use client";

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";

export interface BuiltInTool {
  name: string;
  description: string;
  input_schema?: Record<string, any>;
}

export interface BuiltInToolsResponse {
  tools: BuiltInTool[];
  error?: string;
}

/**
 * Fetch built-in tools from the tools-service MCP server.
 * These are the tools available from the local tools-service.
 */
export default function useBuiltInTools() {
  const { data, error, isLoading, mutate } = useSWR<BuiltInToolsResponse>(
    "/api/proxy/mcp/tools-builtin",
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 30000, // 30 seconds
    }
  );

  return {
    tools: data?.tools ?? [],
    isLoading,
    error: error || data?.error,
    refresh: mutate,
  };
}