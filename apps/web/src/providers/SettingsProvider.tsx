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
import useCCPairs from "@/hooks/useCCPairs";

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
  const vectorDbEnabled = settings.settings.vector_db_enabled !== false;
  const { ccPairs } = useCCPairs(vectorDbEnabled && enableSearchRuntimeStatus);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  /**
   * NOTE (@raunakab):
   * Whether search mode is actually available to users.
   *
   * Prefer `isSearchModeAvailable` over `settings.search_ui_enabled`.
   * The raw setting only captures the admin's *intent*. This derived value
   * also checks runtime prerequisites (connectors must exist) so that
   * consumers don't need to independently verify availability.
   */
  const isSearchModeAvailable = useMemo(
    () =>
      enableSearchRuntimeStatus &&
      settings.settings.search_ui_enabled !== false &&
      ccPairs.length > 0,
    [enableSearchRuntimeStatus, settings.settings.search_ui_enabled, ccPairs.length]
  );

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
