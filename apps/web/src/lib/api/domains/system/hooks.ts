import { systemEndpoints } from "@/lib/api/domains/system/endpoints";
import useSWR from "swr";

import {
  fetchAvailableMailConfigs,
  fetchMailConfigs,
  fetchUserMailSettings,
} from "@/lib/api/domains/system/api";

import type {
  AvailableMailConfig,
  MailConfig,
  PaginatedMailConfigsResponse,
  UseMailConfigsOptions,
  UserMailSettings,
} from "@/lib/api/domains/system/types";

export function useMailConfigs(options?: UseMailConfigsOptions) {
  const path = systemEndpoints.mailConfigsPage(options).browserPath;
  const { data, error, isLoading, mutate } = useSWR<
    PaginatedMailConfigsResponse | MailConfig[]
  >(path, fetchMailConfigs);
  const mailConfigs = Array.isArray(data) ? data : data?.items || [];
  const totalItems = Array.isArray(data) ? data.length : data?.total_items || 0;
  const totalPages = Array.isArray(data)
    ? Math.max(1, Math.ceil(data.length / (options?.pageSize || 10)))
    : data?.total_pages || 1;
  const currentPage = Array.isArray(data)
    ? options?.page || 1
    : data?.page || options?.page || 1;
  return {
    mailConfigs,
    totalItems,
    totalPages,
    currentPage,
    error,
    isLoading,
    refreshMailConfigs: mutate,
  };
}

export function useUserMailSettings() {
  const { data, error, isLoading, mutate } = useSWR<UserMailSettings | null>(
    systemEndpoints.userMailSettings.browserPath,
    fetchUserMailSettings
  );
  return {
    userMailSettings: data ?? null,
    error,
    isLoading,
    refreshUserMailSettings: mutate,
  };
}

export function useAvailableMailConfigs() {
  const { data, error, isLoading } = useSWR<AvailableMailConfig[]>(
    systemEndpoints.availableMailConfigs.browserPath,
    fetchAvailableMailConfigs
  );
  return { availableMailConfigs: data ?? [], error, isLoading };
}
