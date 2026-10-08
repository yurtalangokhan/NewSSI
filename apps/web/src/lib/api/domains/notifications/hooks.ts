import { notificationsEndpoints } from "@/lib/api/domains/notifications/endpoints";
import useSWR, { type SWRConfiguration } from "swr";
import type { Notification } from "@/interfaces/settings";
import { fetchNotifications } from "@/lib/api/domains/notifications/api";

export type { Notification };

/**
 * Thin SWR ownership layer for notifications.
 * Key from endpoints.ts, fetcher from api.ts.
 * Accepts SWR configuration so callers can pass revalidateOnFocus: false etc.
 *
 * Returns both SWR shape (.data, .error, .mutate) and compatibility alias (.notifications).
 */
export function useNotifications(
  options?: SWRConfiguration<Notification[], unknown>
) {
  const swr = useSWR<Notification[]>(
    notificationsEndpoints.listNotifications().browserPath,
    () => fetchNotifications(),
    options
  );
  return {
    data: swr.data,
    notifications: swr.data,
    mutate: swr.mutate,
    error: swr.error,
    isLoading: !swr.error && !swr.data,
  };
}
