"use client";

import {
  AUTH_SESSION_REFRESHED_EVENT,
  authenticatedFetch,
  errorHandlingFetcher,
  RedirectError,
  refreshSessionProactively,
} from "@/lib/fetcher";
import useSWR from "swr";
import Modal from "@/refresh-components/Modal";
import { useCallback, useEffect, useState, useRef } from "react";
import { getSecondsUntilExpiration } from "@/lib/time";
import { refreshToken } from "@/lib/user";
import { NEXT_PUBLIC_CUSTOM_REFRESH_URL } from "@/lib/constants";
import Button from "@/refresh-components/buttons/Button";
import { usePathname, useRouter } from "next/navigation";
import { SvgAlertTriangle, SvgLogOut } from "@opal/icons";
import { Content } from "@opal/layouts";
import { useUser } from "@/providers/UserProvider";

import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";

/** Renew this long before the access token expires. */
const PROACTIVE_REFRESH_LEAD_SECONDS = 60;
/** Never schedule a renewal tighter than this, to avoid a tight retry loop. */
const MIN_REFRESH_DELAY_SECONDS = 5;
const MAX_TIMEOUT_MS = 2 ** 31 - 1;

export default function AppHealthBanner() {
  const router = useRouter();
  const { t } = useTranslation("common", { keyPrefix: "appHealth" });
  const { error } = useSWR("/api/health", errorHandlingFetcher);
  const [expired, setExpired] = useState(false);
  const [showLoggedOutModal, setShowLoggedOutModal] = useState(false);
  const pathname = usePathname();
  const expirationTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const refreshIntervalRef = useRef<NodeJS.Timer | null>(null);

  const { user, refreshUser } = useUser();

  // Function to handle the "Log in" button click
  function handleLogin() {
    setShowLoggedOutModal(false);
    router.push("/auth/login");
  }

  const synchronizeRefreshedSession = useCallback(async () => {
    setExpired(false);
    setShowLoggedOutModal(false);
    await refreshUser();
  }, [refreshUser]);

  const markSessionExpired = useCallback(() => {
    setExpired(true);
    if (!pathname?.includes("/auth")) {
      setShowLoggedOutModal(true);
    }
  }, [pathname]);

  const verifySession = useCallback(async () => {
    try {
      // `/api/health` is a static route that always answers 200, so probing it
      // could never detect an expired session. `/api/me` is authenticated, and
      // `redirectOnAuthError: false` keeps the decision here instead of hard
      // navigating out from under the user.
      const response = await authenticatedFetch("/api/me", {
        redirectOnAuthError: false,
      });
      if (response.ok) {
        await synchronizeRefreshedSession();
        return;
      }
      if (response.status === 401 || response.status === 403) {
        markSessionExpired();
      }
    } catch {
      // Network failure - the backend banner covers this; don't log the user
      // out over a blip.
    }
  }, [markSessionExpired, synchronizeRefreshedSession]);

  useEffect(() => {
    const handleSessionRefreshed = () => {
      void synchronizeRefreshedSession();
    };

    window.addEventListener(
      AUTH_SESSION_REFRESHED_EVENT,
      handleSessionRefreshed
    );
    return () => {
      window.removeEventListener(
        AUTH_SESSION_REFRESHED_EVENT,
        handleSessionRefreshed
      );
    };
  }, [synchronizeRefreshedSession]);

  // Renew slightly before the access token actually dies, so the user never
  // makes a request with an expired token in the first place.
  const setupExpirationTimeout = useCallback(
    (secondsUntilExpiration: number) => {
      // Clear any existing timeout
      if (expirationTimeoutRef.current) {
        clearTimeout(expirationTimeoutRef.current);
      }

      const secondsUntilRefresh = Math.max(
        secondsUntilExpiration - PROACTIVE_REFRESH_LEAD_SECONDS,
        MIN_REFRESH_DELAY_SECONDS
      );
      const delayMs = secondsUntilRefresh * 1000;
      if (delayMs > MAX_TIMEOUT_MS) {
        // setTimeout overflows past ~24.8 days and would fire immediately.
        return;
      }

      expirationTimeoutRef.current = setTimeout(() => {
        void (async () => {
          if (await refreshSessionProactively()) {
            await synchronizeRefreshedSession();
            return;
          }
          await verifySession();
        })();
      }, delayMs);
    },
    [synchronizeRefreshedSession, verifySession]
  );

  // Clean up any timeouts/intervals when component unmounts
  useEffect(() => {
    return () => {
      if (expirationTimeoutRef.current) {
        clearTimeout(expirationTimeoutRef.current);
      }

      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, []);

  // Set up token refresh logic if custom refresh URL exists
  useEffect(() => {
    if (!user) return;

    const secondsUntilExpiration = getSecondsUntilExpiration(user);
    if (secondsUntilExpiration === null) return;

    // Set up expiration timeout based on current user data
    setupExpirationTimeout(secondsUntilExpiration);

    if (NEXT_PUBLIC_CUSTOM_REFRESH_URL) {
      const refreshUrl = NEXT_PUBLIC_CUSTOM_REFRESH_URL;

      const attemptTokenRefresh = async () => {
        let retryCount = 0;
        const maxRetries = 3;

        while (retryCount < maxRetries) {
          try {
            const refreshTokenData = await refreshToken(refreshUrl);
            if (!refreshTokenData) {
              throw new Error("Failed to refresh token");
            }

            const response = await authenticatedFetch(
              "/api/enterprise-settings/refresh-token",
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                },
                body: JSON.stringify(refreshTokenData),
              }
            );
            if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Wait for backend to process the token
            await new Promise((resolve) => setTimeout(resolve, 4000));

            // Get updated user data
            // Refresh user state; timeout recalculation happens when `user` updates.
            await refreshUser();

            break; // Success - exit the retry loop
          } catch (error) {
            console.error(
              `Error refreshing token (attempt ${
                retryCount + 1
              }/${maxRetries}):`,
              error
            );
            retryCount++;

            if (retryCount === maxRetries) {
              console.error("Max retry attempts reached");
            } else {
              // Wait before retrying (exponential backoff)
              await new Promise((resolve) =>
                setTimeout(resolve, Math.pow(2, retryCount) * 1000)
              );
            }
          }
        }
      };

      // Set up refresh interval
      const refreshInterval = 60 * 15; // 15 mins

      // Clear any existing interval
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }

      refreshIntervalRef.current = setInterval(
        attemptTokenRefresh,
        refreshInterval * 1000
      );

      // If we're going to expire before the next refresh, kick off a refresh now
      if (secondsUntilExpiration < refreshInterval) {
        attemptTokenRefresh();
      }
    }
  }, [user, setupExpirationTimeout, refreshUser]);

  // Logged out modal
  if (showLoggedOutModal) {
    return (
      <Modal open>
        <Modal.Content width="sm" height="sm">
          <Modal.Header icon={SvgLogOut} title={t("loggedOutTitle")} />
          <Modal.Body>
            <Text as="p" className="text-sm">
              {t("sessionExpiredMessage")}
            </Text>
          </Modal.Body>
          <Modal.Footer>
            <Button onClick={handleLogin}>{t("logInButton")}</Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    );
  }

  if (!error && !expired) {
    return null;
  }

  if (error instanceof RedirectError || expired) {
    if (!pathname?.includes("/auth")) {
      setShowLoggedOutModal(true);
    }
    return null;
  } else {
    return (
      <div className="fixed top-0 left-0 z-[101] w-full bg-status-error-01 p-3">
        <Content
          icon={SvgAlertTriangle}
          title={t("backendUnavailableTitle")}
          description={t("backendUnavailableDescription")}
          sizePreset="main-content"
          variant="section"
        />
      </div>
    );
  }
}
