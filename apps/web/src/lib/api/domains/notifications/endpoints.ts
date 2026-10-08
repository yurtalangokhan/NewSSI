export type NotificationId = number;

export const notificationsEndpoints = {
  notifications: { browserPath: "/api/notifications" },
  listNotifications: (): { browserPath: string } => {
    return { browserPath: notificationsEndpoints.notifications.browserPath };
  },
  dismissNotification: (
    notificationId: NotificationId
  ): { browserPath: string } => {
    return {
      browserPath: `/api/notifications/${encodeURIComponent(
        String(notificationId)
      )}/dismiss`,
    };
  },
} as const;
