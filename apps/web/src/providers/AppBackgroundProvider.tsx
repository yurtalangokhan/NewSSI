"use client";

import React, { createContext, useContext, useMemo } from "react";
import { useUser } from "@/providers/UserProvider";
import {
  CHAT_BACKGROUND_NONE,
  getBackgroundById,
  ChatBackgroundOption,
} from "@/lib/constants/chatBackgrounds";

interface AppBackgroundContextType {
  /** The full background option object, or undefined if none/invalid */
  appBackground: ChatBackgroundOption | undefined;
  /** The URL of the background image, or null if no background is set */
  appBackgroundUrl: string | null;
  /** Whether a background is currently active */
  hasBackground: boolean;
  foregroundTextClass: string;
  foregroundMutedTextClass: string;
  foregroundIconClass: string;
  foregroundBorderClass: string;
  foregroundTextStyle: React.CSSProperties;
  foregroundMutedTextStyle: React.CSSProperties;
  foregroundIconStyle: React.CSSProperties;
  foregroundBorderStyle: React.CSSProperties;
}

const AppBackgroundContext = createContext<
  AppBackgroundContextType | undefined
>(undefined);

export function AppBackgroundProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = useUser();

  const value = useMemo(() => {
    const chatBackgroundId = user?.preferences?.chat_background;
    const appBackground = getBackgroundById(chatBackgroundId ?? null);
    const hasBackground =
      !!appBackground && appBackground.src !== CHAT_BACKGROUND_NONE;
    const appBackgroundUrl = hasBackground ? appBackground.src : null;
    const isDarkBackground = appBackground?.isDarkBackground === true;
    const foregroundTextClass = isDarkBackground
      ? "text-text-inverted-05"
      : "text-text-05";
    const foregroundMutedTextClass = isDarkBackground
      ? "text-text-inverted-03"
      : "text-text-03";
    const foregroundIconClass = isDarkBackground
      ? "stroke-text-inverted-05"
      : "stroke-text-05";
    const foregroundBorderClass = isDarkBackground
      ? "border-text-inverted-03"
      : "border-border-01";
    const foregroundTextStyle = {
      color: isDarkBackground ? "var(--text-inverted-05)" : "var(--text-05)",
    };
    const foregroundMutedTextStyle = {
      color: isDarkBackground ? "var(--text-inverted-03)" : "var(--text-03)",
    };
    const foregroundIconStyle = {
      stroke: isDarkBackground ? "var(--text-inverted-05)" : "var(--text-05)",
    };
    const foregroundBorderStyle = {
      borderColor: isDarkBackground
        ? "var(--text-inverted-03)"
        : "var(--border-01)",
    };

    return {
      appBackground,
      appBackgroundUrl,
      hasBackground,
      foregroundTextClass,
      foregroundMutedTextClass,
      foregroundIconClass,
      foregroundBorderClass,
      foregroundTextStyle,
      foregroundMutedTextStyle,
      foregroundIconStyle,
      foregroundBorderStyle,
    };
  }, [user?.preferences?.chat_background]);

  return (
    <AppBackgroundContext.Provider value={value}>
      {children}
    </AppBackgroundContext.Provider>
  );
}

export function useAppBackground() {
  const context = useContext(AppBackgroundContext);
  if (context === undefined) {
    throw new Error(
      "useAppBackground must be used within an AppBackgroundProvider"
    );
  }
  return context;
}
