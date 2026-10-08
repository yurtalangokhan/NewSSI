"use client";

import { useContext } from "react";

import { SettingsContext } from "@/providers/SettingsProvider";

export type CustomAnalyticsStatus = {
  customAnalyticsEnabled: boolean;
  isLoading: boolean;
};

/**
 * Whether custom analytics is configured for this deployment.
 *
 * The underlying CUSTOM_ANALYTICS_SECRET_KEY is server-only, so this reads the
 * flag the server put on `CombinedSettings`. Reading the variable here directly
 * always returned `false` in the browser, which is why the admin sidebar entry
 * never appeared.
 */
export function useCustomAnalyticsEnabled(): CustomAnalyticsStatus {
  const settings = useContext(SettingsContext);

  return {
    customAnalyticsEnabled: settings?.customAnalyticsEnabled ?? false,
    isLoading: settings === null,
  };
}
