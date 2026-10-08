import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";

import {
  fetchSlackBot,
  fetchSlackBots,
  fetchSlackChannelConfigs,
  fetchSlackChannelConfigsByBot,
} from "@/lib/api/domains/integrations/api";
import { SlackBot, SlackChannelConfig } from "@/lib/types";
import useSWR, { mutate } from "swr";

export const useSlackChannelConfigs = () => {
  const url = integrationsEndpoints.listSlackChannels.browserPath;
  const swrResponse = useSWR<SlackChannelConfig[]>(url, () =>
    fetchSlackChannelConfigs<SlackChannelConfig[]>()
  );

  return {
    ...swrResponse,
    refreshSlackChannelConfigs: () => mutate(url),
  };
};

export const useSlackBots = () => {
  const url = integrationsEndpoints.createSlackBot.browserPath;
  const swrResponse = useSWR<SlackBot[]>(url, () =>
    fetchSlackBots<SlackBot[]>()
  );

  return {
    ...swrResponse,
    refreshSlackBots: () => mutate(url),
  };
};

export const useSlackBot = (botId: number) => {
  const url = integrationsEndpoints.fetchSlackBot(String(botId)).browserPath;
  const swrResponse = useSWR<SlackBot>(url, () =>
    fetchSlackBot<SlackBot>(botId)
  );

  return {
    ...swrResponse,
    refreshSlackBot: () => mutate(url),
  };
};

export const useSlackChannelConfigsByBot = (botId: number) => {
  const url = integrationsEndpoints.slackChannelConfigByEncodedBot(
    String(botId)
  ).browserPath;
  const swrResponse = useSWR<SlackChannelConfig[]>(url, () =>
    fetchSlackChannelConfigsByBot<SlackChannelConfig[]>(botId)
  );

  return {
    ...swrResponse,
    refreshSlackChannelConfigs: () => mutate(url),
  };
};
