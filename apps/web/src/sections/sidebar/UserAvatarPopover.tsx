"use client";

import { useState } from "react";
import { ANONYMOUS_USER_NAME, LOGOUT_DISABLED } from "@/lib/constants";
import { Notification } from "@/interfaces/settings";
import useSWR, { preload } from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { checkUserIsNoAuthUser, logout } from "@/lib/user";
import { useUser } from "@/providers/UserProvider";
import InputAvatar from "@/refresh-components/inputs/InputAvatar";
import Text from "@/refresh-components/texts/Text";
import LineItem from "@/refresh-components/buttons/LineItem";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import SidebarTab from "@/refresh-components/buttons/SidebarTab";
import NotificationsPopover from "@/sections/sidebar/NotificationsPopover";
import {
  SvgBell,
  SvgExternalLink,
  SvgLogOut,
  SvgUser,
  SvgNotificationBubble,
} from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import { toast } from "@/hooks/useToast";
import useAppFocus from "@/hooks/useAppFocus";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useTranslation } from "react-i18next";

function getDisplayName(email?: string, personalName?: string): string {
  // Prioritize custom personal name if set
  if (personalName && personalName.trim()) {
    return personalName.trim();
  }

  // Fallback to email-derived username
  if (!email) return ANONYMOUS_USER_NAME;
  const atIndex = email.indexOf("@");
  if (atIndex <= 0) return ANONYMOUS_USER_NAME;

  return email.substring(0, atIndex);
}

function getPreferredName(user: {
  email?: string;
  first_name?: string | null;
  full_name?: string | null;
  personalization?: { name?: string };
} | null): string {
  if (!user) return ANONYMOUS_USER_NAME;
  if (user.full_name && user.full_name.trim()) return user.full_name.trim();
  if (user.first_name && user.first_name.trim()) return user.first_name.trim();
  return getDisplayName(user.email, user.personalization?.name);
}

interface SettingsPopoverProps {
  onUserSettingsClick: () => void;
  onOpenNotifications: () => void;
}

function SettingsPopover({
  onUserSettingsClick,
  onOpenNotifications,
}: SettingsPopoverProps) {
  const { user } = useUser();
  const { t } = useTranslation();
  const { data: notifications } = useSWR<Notification[]>(
    "/api/notifications",
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const undismissedCount =
    notifications?.filter((n) => !n.dismissed).length ?? 0;
  const isAnonymousUser =
    user?.is_anonymous_user || checkUserIsNoAuthUser(user?.id ?? "");
  const showLogout = user && !isAnonymousUser && !LOGOUT_DISABLED;
  const showLogin = isAnonymousUser;

  const handleLogin = () => {
    const currentUrl = `${pathname}${
      searchParams?.toString() ? `?${searchParams.toString()}` : ""
    }`;
    const encodedRedirect = encodeURIComponent(currentUrl);
    router.push(`/auth/login?next=${encodedRedirect}`);
  };

  const handleLogout = () => {
    logout().catch(() => {
      toast.error(t("userMenu.logoutFailed"));
    });
  };

  return (
    <>
      <PopoverMenu>
        {[
          <div key="user-settings" data-testid="Settings/user-settings">
            <LineItem
              icon={SvgUser}
              href="/app/settings"
              onClick={onUserSettingsClick}
            >
              {t("userMenu.userSettings")}
            </LineItem>
          </div>,
          <LineItem
            key="notifications"
            icon={SvgBell}
            onClick={onOpenNotifications}
          >
            {undismissedCount > 0
              ? t("userMenu.notificationsWithCount", { count: undismissedCount })
              : t("userMenu.notifications")}
          </LineItem>,
          <LineItem
            key="help-faq"
            icon={SvgExternalLink}
            href="https://docs.onyx.app"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("userMenu.helpFaq")}
          </LineItem>,
          <div key="language-switcher">
            <LanguageSwitcher />
          </div>,
          null,
          showLogin && (
            <LineItem key="log-in" icon={SvgUser} onClick={handleLogin}>
              {t("userMenu.logIn")}
            </LineItem>
          ),
          showLogout && (
            <LineItem
              key="log-out"
              icon={SvgLogOut}
              danger
              onClick={handleLogout}
            >
              {t("userMenu.logOut")}
            </LineItem>
          ),
        ]}
      </PopoverMenu>
    </>
  );
}

export interface SettingsProps {
  folded?: boolean;
  onShowBuildIntro?: () => void;
}

export default function UserAvatarPopover({
  folded,
  onShowBuildIntro,
}: SettingsProps) {
  const [popupState, setPopupState] = useState<
    "Settings" | "Notifications" | undefined
  >(undefined);
  const { user } = useUser();
  const router = useRouter();
  const appFocus = useAppFocus();
  const settings = useSettingsContext();
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;

  // Fetch notifications for display
  // The GET endpoint also triggers a refresh if release notes are stale
  const { data: notifications } = useSWR<Notification[]>(
    "/api/notifications",
    errorHandlingFetcher
  );

  const displayName = getPreferredName(user);
  const undismissedCount =
    notifications?.filter((n) => !n.dismissed).length ?? 0;
  const hasNotifications = undismissedCount > 0;

  const handlePopoverOpen = (state: boolean) => {
    if (state) {
      // Prefetch user settings data when popover opens for instant modal display
      preload("/api/federated/oauth-status", errorHandlingFetcher);
      if (vectorDbEnabled) {
        preload("/api/manage/connector-status", errorHandlingFetcher);
      }
      preload("/api/llm/provider", errorHandlingFetcher);
      setPopupState("Settings");
    } else {
      setPopupState(undefined);
    }
  };

  return (
    <Popover open={!!popupState} onOpenChange={handlePopoverOpen}>
      <Popover.Trigger asChild>
        <div id="onyx-user-dropdown">
          <SidebarTab
            leftIcon={({ className }) => (
              <InputAvatar
                className={cn(
                  "flex items-center justify-center bg-background-neutral-inverted-00",
                  className,
                  "w-5 h-5"
                )}
              >
                <Text as="p" inverted secondaryBody>
                  {displayName[0]?.toUpperCase()}
                </Text>
              </InputAvatar>
            )}
            rightChildren={
              hasNotifications ? (
                <Section padding={0.5}>
                  <SvgNotificationBubble size={6} />
                </Section>
              ) : undefined
            }
            transient={!!popupState || appFocus.isUserSettings()}
            folded={folded}
          >
            {displayName}
          </SidebarTab>
        </div>
      </Popover.Trigger>

      <Popover.Content
        align="end"
        side="right"
        width={popupState === "Notifications" ? "xl" : "md"}
      >
        {popupState === "Settings" && (
          <SettingsPopover
            onUserSettingsClick={() => {
              setPopupState(undefined);
            }}
            onOpenNotifications={() => setPopupState("Notifications")}
          />
        )}
        {popupState === "Notifications" && (
          <NotificationsPopover
            onClose={() => setPopupState("Settings")}
            onNavigate={() => setPopupState(undefined)}
            onShowBuildIntro={onShowBuildIntro}
          />
        )}
      </Popover.Content>
    </Popover>
  );
}
