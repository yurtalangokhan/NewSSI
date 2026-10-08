"use client";
import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";

import {
  fetchDiscordChannels,
  fetchDiscordGuild,
  fetchDiscordGuilds,
  fetchDiscordManagedConfig,
} from "@/lib/api/domains/integrations/api";

import useSWR from "swr";
import {
  DiscordBotConfig,
  DiscordGuildConfig,
  DiscordChannelConfig,
} from "@/lib/api/domains/integrations/discord-types";

const BASE_URL = integrationsEndpoints.base.browserPath;

/**
 * Custom fetcher for bot config that handles 403 specially.
 * 403 means bot config is managed externally (Cloud or env var).
 */
async function botConfigFetcher(url: string): Promise<DiscordBotConfig | null> {
  const res = await fetchDiscordManagedConfig();

  if (res.status === 403) {
    // Bot config is managed externally - return null to indicate not accessible
    return null;
  }

  if (!res.ok) {
    throw new Error("Failed to fetch bot config");
  }

  return res.json();
}

/**
 * Hook for bot config. Returns null when managed externally (Cloud/env var).
 */
export function useDiscordBotConfig() {
  const url = `${BASE_URL}/config`;
  const swrResponse = useSWR<DiscordBotConfig | null>(url, botConfigFetcher);
  return {
    ...swrResponse,
    // null = managed externally (403), undefined = loading
    isManaged: swrResponse.data === null,
    refreshBotConfig: () => swrResponse.mutate(),
  };
}

export function useDiscordGuilds() {
  const url = `${BASE_URL}/guilds`;
  const swrResponse = useSWR<DiscordGuildConfig[]>(url, () =>
    fetchDiscordGuilds<DiscordGuildConfig[]>()
  );
  return {
    ...swrResponse,
    refreshGuilds: () => swrResponse.mutate(),
  };
}

export function useDiscordGuild(configId: number) {
  const url = `${BASE_URL}/guilds/${configId}`;
  const swrResponse = useSWR<DiscordGuildConfig>(url, () =>
    fetchDiscordGuild<DiscordGuildConfig>(configId)
  );
  return {
    ...swrResponse,
    refreshGuild: () => swrResponse.mutate(),
  };
}

export function useDiscordChannels(guildConfigId: number) {
  const url = guildConfigId
    ? `${BASE_URL}/guilds/${guildConfigId}/channels`
    : null;
  const swrResponse = useSWR<DiscordChannelConfig[]>(url, () =>
    fetchDiscordChannels<DiscordChannelConfig[]>(guildConfigId)
  );
  return {
    ...swrResponse,
    refreshChannels: () => swrResponse.mutate(),
  };
}
