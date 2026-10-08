"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useSettingsContext } from "@/providers/SettingsProvider";
import { useUser } from "@/providers/UserProvider";

/**
 * How a new session handles the user's input:
 * - **chat**: a conversation with the selected agent.
 * - **search**: the knowledge search page over documents and knowledge graphs.
 */
export type AppMode = "chat" | "search";

interface AppModeContextValue {
  appMode: AppMode;
  setAppMode: (mode: AppMode) => void;
  /** Whether the admin allows search mode (`search_ui_enabled`). */
  isSearchAvailable: boolean;
  /** Changes whenever the search page must start over (new session). */
  searchSessionKey: number;
  /** Drop the explicit mode choice so the persisted preference applies again. */
  resetModeChoice: () => void;
  /** Begin a new session: reset the mode choice and start a fresh search page. */
  startNewSession: () => void;
}

export const AppModeContext = createContext<AppModeContextValue>({
  appMode: "chat",
  setAppMode: () => undefined,
  isSearchAvailable: false,
  searchSessionKey: 0,
  resetModeChoice: () => undefined,
  startNewSession: () => undefined,
});

export function useAppMode(): AppModeContextValue {
  return useContext(AppModeContext);
}

/** The mode a new session opens in for a persisted `default_app_mode`. */
export function appModeFromPreference(
  preference: string | null | undefined
): AppMode {
  return preference === "SEARCH" ? "search" : "chat";
}

/**
 * Reopens in the preferred mode whenever the page is (re-)entered as a new
 * session, so a mode picked in an earlier session never leaks into the next.
 * The search page is left alone: it is not mounted while another session shows.
 */
export function useStartNewSessionOnEntry(isNewSession: boolean): void {
  const { resetModeChoice } = useAppMode();

  useEffect(() => {
    if (isNewSession) resetModeChoice();
  }, [isNewSession, resetModeChoice]);
}

export interface AppModeProviderProps {
  children: React.ReactNode;
}

export function AppModeProvider({ children }: AppModeProviderProps) {
  const { user } = useUser();
  const { isSearchModeAvailable } = useSettingsContext();
  const preferredMode = appModeFromPreference(
    user?.preferences?.default_app_mode
  );
  // The mode is derived, never copied into state from an effect, so the first
  // render is already in its final mode instead of flipping after mount.
  const [userChoice, setUserChoice] = useState<AppMode | null>(null);
  const [searchSessionKey, setSearchSessionKey] = useState(0);
  const appMode: AppMode = isSearchModeAvailable
    ? userChoice ?? preferredMode
    : "chat";

  const setAppMode = useCallback(
    (mode: AppMode) => {
      if (mode === "search" && !isSearchModeAvailable) return;
      setUserChoice(mode);
    },
    [isSearchModeAvailable]
  );

  const resetModeChoice = useCallback(() => setUserChoice(null), []);

  const startNewSession = useCallback(() => {
    resetModeChoice();
    setSearchSessionKey((key) => key + 1);
  }, [resetModeChoice]);

  const value = useMemo(
    () => ({
      appMode,
      setAppMode,
      isSearchAvailable: isSearchModeAvailable,
      searchSessionKey,
      resetModeChoice,
      startNewSession,
    }),
    [
      appMode,
      setAppMode,
      isSearchModeAvailable,
      searchSessionKey,
      resetModeChoice,
      startNewSession,
    ]
  );

  return (
    <AppModeContext.Provider value={value}>{children}</AppModeContext.Provider>
  );
}
