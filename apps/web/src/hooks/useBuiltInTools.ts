"use client";

import useSWR from "swr";
import { useTranslation } from "react-i18next";
import { authenticatedFetch, FetchError, getDefaultErrorMsg } from "@/lib/fetcher";

export interface BuiltInTool {
  name: string;
  description: string;
  input_schema?: Record<string, any>;
}

export interface BuiltInToolsResponse {
  tools: BuiltInTool[];
  error?: string;
}

async function fetchBuiltInTools([url, language]: [
  string,
  string,
]): Promise<BuiltInToolsResponse> {
  const res = await authenticatedFetch(url, {
    headers: { "X-Language": language, "Accept-Language": language },
  });

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }

  if (!res.ok) {
    throw new FetchError(getDefaultErrorMsg(), res.status, payload);
  }

  return payload as BuiltInToolsResponse;
}

/**
 * Fetch built-in tools from the tools-service MCP server.
 * These are the tools available from the local tools-service.
 *
 * The response is translated server-side based on the app's selected
 * language, so the language is sent as a header and included in the SWR
 * key to force a refetch whenever it changes.
 */
export default function useBuiltInTools() {
  const { i18n } = useTranslation();
  const { data, error, isLoading, mutate } = useSWR<BuiltInToolsResponse>(
    ["/api/proxy/mcp/tools-builtin", i18n.language],
    fetchBuiltInTools,
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