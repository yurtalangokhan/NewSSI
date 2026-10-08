import { notificationsEndpoints } from "@/lib/api/domains/notifications/endpoints";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";
import type { Notification } from "@/interfaces/settings";

import type { NotificationId } from "@/lib/api/domains/notifications/endpoints";

/**
 * Fetches notifications matching errorHandlingFetcher contract:
 * - X-Language added by apiRequest internally
 * - Throws FetchError for non-OK responses
 * - Returns parsed JSON or [] on parse failure
 */
export async function fetchNotifications(): Promise<Notification[]> {
  const res = await apiRequest(
    notificationsEndpoints.listNotifications().browserPath
  );
  if (!res.ok) {
    const parsedError = await parseApiErrorResponse(res);
    throw new FetchError(
      parsedError.userMessage,
      res.status,
      parsedError.raw,
      parsedError
    );
  }
  try {
    const data = await res.json();
    return (data ?? []) as Notification[];
  } catch {
    return [] as Notification[];
  }
}

export async function dismissNotification(
  notificationId: NotificationId
): Promise<Response> {
  return apiRequest(
    notificationsEndpoints.dismissNotification(notificationId).browserPath,
    {
      method: "POST",
    }
  );
}
