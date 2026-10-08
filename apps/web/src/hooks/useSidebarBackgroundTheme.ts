"use client";

import createDeviceFlagHook from "@/hooks/createDeviceFlagHook";

/**
 * Whether the app sidebar takes on the TÜRKSAT theme colors while an animated
 * (canvas) chat background is showing, and a setter. A device-level display
 * preference that defaults to on.
 */
const useSidebarBackgroundTheme = createDeviceFlagHook({
  storageKey: "agentic_sidebar_background_theme",
  changeEvent: "agentic:sidebar-background-theme-change",
});

export default useSidebarBackgroundTheme;
