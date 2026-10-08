"use client";
import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";
import { useEffect } from "react";
import { appSettings } from "@/lib/settings";

const isPostHogEnabled = appSettings.NEXT_PUBLIC_POSTHOG_KEY !== undefined;

type PHProviderProps = { children: React.ReactNode };

export function PHProvider({ children }: PHProviderProps) {
  useEffect(() => {
    if (isPostHogEnabled) {
      posthog.init(appSettings.NEXT_PUBLIC_POSTHOG_KEY!, {
        api_host: "/ph_ingest",
        ui_host: appSettings.NEXT_PUBLIC_POSTHOG_HOST,
        person_profiles: "identified_only",
        capture_pageview: false,
        session_recording: {
          // Sensitive inputs should use data-ph-no-capture attribute
          maskAllInputs: false,
        },
      });
    }
  }, []);

  if (!isPostHogEnabled) {
    return <>{children}</>;
  }

  return <PostHogProvider client={posthog}>{children}</PostHogProvider>;
}
