import { systemEndpoints } from "@/lib/api/domains/system/endpoints";

import {
  fetchAdminAtlasBotAnalytics,
  fetchAdminQueryAnalytics,
  fetchAdminUserAnalytics,
  fetchPersonaMessagesAnalytics,
  fetchPersonaUniqueUsersAnalytics,
} from "@/lib/api/domains/system/api";
import useSWR, { mutate } from "swr";
import {
  AtlasBotAnalytics,
  QueryAnalytics,
  UserAnalytics,
} from "./usage/types";
import { useState } from "react";
import { buildApiPath } from "@/lib/urlBuilder";

import {
  convertDateToEndOfDay,
  convertDateToStartOfDay,
  getXDaysAgo,
} from "../../../../components/dateRangeSelectors/dateUtils";
import { THIRTY_DAYS } from "../../../../components/dateRangeSelectors/AdminDateRangeSelector";
import { DateRangePickerValue } from "@/lib/api/domains/knowledge/types";

export const useTimeRange = () => {
  return useState<DateRangePickerValue>({
    to: new Date(),
    from: getXDaysAgo(30),
    selectValue: THIRTY_DAYS,
  });
};

export const useQueryAnalytics = (timeRange: DateRangePickerValue) => {
  const url = buildApiPath(systemEndpoints.analyticsAdminQuery.browserPath, {
    start: convertDateToStartOfDay(timeRange.from)?.toISOString(),
    end: convertDateToEndOfDay(timeRange.to)?.toISOString(),
  });
  const swrResponse = useSWR<QueryAnalytics[]>(url, () =>
    fetchAdminQueryAnalytics<QueryAnalytics[]>(
      convertDateToStartOfDay(timeRange.from)?.toISOString(),
      convertDateToEndOfDay(timeRange.to)?.toISOString()
    )
  );

  return {
    ...swrResponse,
    refreshQueryAnalytics: () => mutate(url),
  };
};

export const useUserAnalytics = (timeRange: DateRangePickerValue) => {
  const url = buildApiPath(systemEndpoints.analyticsAdminUser.browserPath, {
    start: convertDateToStartOfDay(timeRange.from)?.toISOString(),
    end: convertDateToEndOfDay(timeRange.to)?.toISOString(),
  });
  const swrResponse = useSWR<UserAnalytics[]>(url, () =>
    fetchAdminUserAnalytics<UserAnalytics[]>(
      convertDateToStartOfDay(timeRange.from)?.toISOString(),
      convertDateToEndOfDay(timeRange.to)?.toISOString()
    )
  );

  return {
    ...swrResponse,
    refreshUserAnalytics: () => mutate(url),
  };
};

export const useAtlasBotAnalytics = (timeRange: DateRangePickerValue) => {
  const url = buildApiPath(systemEndpoints.analyticsAdminAtlasbot.browserPath, {
    start: convertDateToStartOfDay(timeRange.from)?.toISOString(),
    end: convertDateToEndOfDay(timeRange.to)?.toISOString(),
  });
  const swrResponse = useSWR<AtlasBotAnalytics[]>(url, () =>
    fetchAdminAtlasBotAnalytics<AtlasBotAnalytics[]>(
      convertDateToStartOfDay(timeRange.from)?.toISOString(),
      convertDateToEndOfDay(timeRange.to)?.toISOString()
    )
  ); // TODO

  return {
    ...swrResponse,
    refreshAtlasBotAnalytics: () => mutate(url),
  };
};

export function getDatesList(startDate: Date): string[] {
  const datesList: string[] = [];
  const endDate = new Date(); // current date

  for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
    const dateStr = d.toISOString().split("T")[0]; // convert date object to 'YYYY-MM-DD' format
    if (dateStr !== undefined) {
      datesList.push(dateStr);
    }
  }

  return datesList;
}

export interface PersonaMessageAnalytics {
  total_messages: number;
  date: string;
  persona_id: number;
}

export interface PersonaSnapshot {
  id: number;
  name: string;
  description: string;
  is_visible: boolean;
  is_public: boolean;
}

export const usePersonaMessages = (
  personaId: number | undefined,
  timeRange: DateRangePickerValue
) => {
  const url = buildApiPath(
    systemEndpoints.analyticsAdminPersonaMessages.browserPath,
    {
      persona_id: personaId?.toString(),
      start: convertDateToStartOfDay(timeRange.from)?.toISOString(),
      end: convertDateToEndOfDay(timeRange.to)?.toISOString(),
    }
  );

  const { data, error, isLoading } = useSWR<PersonaMessageAnalytics[]>(
    personaId !== undefined ? url : null,
    () =>
      fetchPersonaMessagesAnalytics<PersonaMessageAnalytics[]>(
        personaId!,
        convertDateToStartOfDay(timeRange.from)?.toISOString(),
        convertDateToEndOfDay(timeRange.to)?.toISOString()
      )
  );

  return {
    data,
    error,
    isLoading,
    refreshPersonaMessages: () => mutate(url),
  };
};

export interface PersonaUniqueUserAnalytics {
  unique_users: number;
  date: string;
  persona_id: number;
}

export const usePersonaUniqueUsers = (
  personaId: number | undefined,
  timeRange: DateRangePickerValue
) => {
  const url = buildApiPath(
    systemEndpoints.analyticsAdminPersonaUniqueUsers.browserPath,
    {
      persona_id: personaId?.toString(),
      start: convertDateToStartOfDay(timeRange.from)?.toISOString(),
      end: convertDateToEndOfDay(timeRange.to)?.toISOString(),
    }
  );

  const { data, error, isLoading } = useSWR<PersonaUniqueUserAnalytics[]>(
    personaId !== undefined ? url : null,
    () =>
      fetchPersonaUniqueUsersAnalytics<PersonaUniqueUserAnalytics[]>(
        personaId!,
        convertDateToStartOfDay(timeRange.from)?.toISOString(),
        convertDateToEndOfDay(timeRange.to)?.toISOString()
      )
  );

  return {
    data,
    error,
    isLoading,
    refreshPersonaUniqueUsers: () => mutate(url),
  };
};
