"use client";

import { CombinedSettings } from "@/interfaces/settings";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useMemo,
  JSX,
} from "react";

export function SettingsProvider({
  children,
  settings,
  enableSearchRuntimeStatus = true,
}: {
  children: React.ReactNode | JSX.Element;
  settings: CombinedSettings;
  enableSearchRuntimeStatus?: boolean;
}) {
  const [isMobile, setIsMobile] = useState<boolean | undefined>();

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  /**
   * Whether the knowledge search mode is offered in the app shell.
   *
   * Prefer `isSearchModeAvailable` over `settings.search_ui_enabled`: the raw
   * setting is the admin's intent, and search only runs inside the app shell.
   * The search page itself handles users without searchable collections.
   */
  const isSearchModeAvailable =
    enableSearchRuntimeStatus && settings.settings.search_ui_enabled !== false;

  const contextValue = useMemo(
    () => ({ ...settings, isMobile, isSearchModeAvailable }),
    [settings, isMobile, isSearchModeAvailable]
  );

  return (
    <SettingsContext.Provider value={contextValue}>
      {children}
    </SettingsContext.Provider>
  );
}

export const SettingsContext = createContext<CombinedSettings | null>(null);

export function useSettingsContext() {
  const context = useContext(SettingsContext);
  if (context === null) {
    throw new Error(
      "useSettingsContext must be used within a SettingsProvider"
    );
  }
  return context;
}
