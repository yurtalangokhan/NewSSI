"use client";

import { authenticatedFetch } from "@/lib/fetcher";
import { useState, useEffect, useContext } from "react";
import { CustomTooltip } from "../tooltip/CustomTooltip";
import { SettingsContext } from "@/providers/SettingsProvider";
import Link from "next/link";
import type { Route } from "next";
import Cookies from "js-cookie";
import { SvgX } from "@opal/icons";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
const DISMISSED_NOTIFICATION_COOKIE_PREFIX = "dismissed_notification_";
const COOKIE_EXPIRY_DAYS = 1;

export function AnnouncementBanner() {
  const settings = useContext(SettingsContext);
  const { t } = useTranslation();
  const [localNotifications, setLocalNotifications] = useState(
    settings?.settings.notifications || []
  );

  useEffect(() => {
    const filteredNotifications = (
      settings?.settings.notifications || []
    ).filter(
      (notification) =>
        !Cookies.get(
          `${DISMISSED_NOTIFICATION_COOKIE_PREFIX}${notification.id}`
        )
    );
    setLocalNotifications(filteredNotifications);
  }, [settings?.settings.notifications]);

  if (!localNotifications || localNotifications.length === 0) return null;

  const handleDismiss = async (notificationId: number) => {
    try {
      const response = await authenticatedFetch(
        `/api/notifications/${notificationId}/dismiss`,
        {
          method: "POST",
        }
      );
      if (response.ok) {
        Cookies.set(
          `${DISMISSED_NOTIFICATION_COOKIE_PREFIX}${notificationId}`,
          "true",
          { expires: COOKIE_EXPIRY_DAYS }
        );
        setLocalNotifications((prevNotifications) =>
          prevNotifications.filter(
            (notification) => notification.id !== notificationId
          )
        );
      } else {
        console.error("Failed to dismiss notification");
      }
    } catch (error) {
      console.error("Error dismissing notification:", error);
    }
  };

  return (
    <>
      {localNotifications
        .filter((notification) => !notification.dismissed)
        .map((notification) => {
          return (
            <div
              key={notification.id}
              className="absolute top-0 left-1/2 transform -translate-x-1/2 bg-blue-600 rounded-sm text-white px-4 pr-8 py-3 mx-auto"
            >
              {notification.notif_type == "reindex" ? (
                <Text as="p" className="text-center">
                  {t("header.reindexBanner")}{" "}
                  <Link
                    href={"/admin/configuration/search"}
                    className="ml-2 underline cursor-pointer"
                  >
                    {t("header.reindexUpdateLink")}
                  </Link>
                </Text>
              ) : notification.notif_type == "two_day_trial_ending" ? (
                <Text as="p" className="text-center">
                  {t("header.trialEndingBanner")}{" "}
                  <Link
                    href={"/admin/billing" as Route}
                    className="ml-2 underline cursor-pointer"
                  >
                    {t("header.trialUpdateLink")}
                  </Link>
                </Text>
              ) : null}
              <button
                onClick={() => handleDismiss(notification.id)}
                className="absolute top-0 right-0 mt-2 mr-2"
                aria-label={t("header.dismissTooltip")}
              >
                <CustomTooltip
                  showTick
                  citation
                  delay={100}
                  content={t("header.dismissTooltip")}
                >
                  <SvgX className="stroke-text-04 h-5 w-5" />
                </CustomTooltip>
              </button>
            </div>
          );
        })}
    </>
  );
}
