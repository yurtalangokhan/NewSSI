"use client";

import useAppFocus from "@/hooks/useAppFocus";
import useSidebarBackgroundTheme from "@/hooks/useSidebarBackgroundTheme";
import { useAppBackground } from "@/providers/AppBackgroundProvider";

/**
 * Whether the app sidebar should wear the TÜRKSAT theme colors right now: an
 * animated TÜRKSAT background is showing, this part of the app paints it, and
 * the device-level switch in general settings is on.
 */
export default function useTurksatSidebarTheme(): boolean {
  const { appBackgroundCanvas } = useAppBackground();
  const [enabled] = useSidebarBackgroundTheme();
  const appFocus = useAppFocus();

  return enabled && !!appBackgroundCanvas && appFocus.showsChatBackground();
}
