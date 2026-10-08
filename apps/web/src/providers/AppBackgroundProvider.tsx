"use client";

import React, {
  createContext,
  useContext,
  useMemo,
  useState,
  useEffect,
} from "react";
import useBackgroundAnimation from "@/hooks/useBackgroundAnimation";
import useResolvedColorMode from "@/hooks/useResolvedColorMode";
import { useUser } from "@/providers/UserProvider";
import {
  CHAT_BACKGROUND_NONE,
  getBackgroundById,
  isCanvasBackground,
  isNoBackground,
  ChatBackgroundOption,
} from "@/lib/constants/chatBackgrounds";
import {
  getChatBackgroundCookie,
  setChatBackgroundCookie,
  clearChatBackgroundCookie,
  preloadChatBackgroundImage,
} from "@/lib/chatBackgroundClient";
import type {
  TurksatCompany,
  TurksatMode,
} from "@/lib/turksatBackgrounds/types";

/** A background option with its darkness resolved: fixed for a photo, and
 * following the current color mode for a canvas scene. */
export type ResolvedChatBackground = ChatBackgroundOption & {
  isDarkBackground?: boolean;
};

interface AppBackgroundContextType {
  /** The full background option object, or undefined if none/invalid. */
  appBackground: ResolvedChatBackground | undefined;
  /** The URL of the background image, or null if no background is set or
   * the active background is canvas-kind (see `appBackgroundCanvas`). */
  appBackgroundUrl: string | null;
  /** The active TÜRKSAT scene to render, or null if no canvas-kind
   * background is set. Mutually exclusive with `appBackgroundUrl`. */
  appBackgroundCanvas: {
    company: TurksatCompany;
    mode: TurksatMode;
    /** False when the user turned background animation off: the scene is
     * painted once as a still frame. */
    animate: boolean;
  } | null;
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
  initialBackgroundId,
  children,
}: {
  initialBackgroundId?: string | null;
  children: React.ReactNode;
}) {
  const { user } = useUser();
  const colorMode = useResolvedColorMode();
  const [animateCanvas] = useBackgroundAnimation();

  // Initialize with initialBackgroundId from SSR or client cookie to prevent hydration delay
  const [activeBgId, setActiveBgId] = useState<string | null>(() => {
    return (
      user?.preferences?.chat_background ??
      initialBackgroundId ??
      getChatBackgroundCookie()
    );
  });

  // Sync state whenever user preference loads or changes
  useEffect(() => {
    if (user?.preferences?.chat_background !== undefined) {
      const current = user.preferences.chat_background;
      setActiveBgId(current);
      if (current && current !== CHAT_BACKGROUND_NONE) {
        setChatBackgroundCookie(current);
      } else {
        clearChatBackgroundCookie();
      }
    }
  }, [user?.preferences?.chat_background]);

  const effectiveBackgroundId =
    user?.preferences?.chat_background !== undefined
      ? user.preferences.chat_background
      : activeBgId;

  const value = useMemo(() => {
    const option = getBackgroundById(effectiveBackgroundId ?? null);
    const hasBackground = !isNoBackground(option);
    const canvasOption = option && isCanvasBackground(option) ? option : null;
    const appBackgroundCanvas = canvasOption
      ? {
          company: canvasOption.canvas.company,
          mode: colorMode,
          animate: animateCanvas,
        }
      : null;
    const appBackground: ResolvedChatBackground | undefined = canvasOption
      ? { ...canvasOption, isDarkBackground: colorMode === "dark" }
      : option;
    const appBackgroundUrl =
      hasBackground && option && !isCanvasBackground(option)
        ? option.src
        : null;
    const isDarkBackground = appBackground?.isDarkBackground === true;
    // These use the theme-independent "light"/"dark" tokens (always literal
    // white/black) rather than the "inverted" tokens, which flip meaning
    // depending on the *current theme* rather than the background image.
    // Contrast against a background photo must not depend on light/dark mode.
    // They must only be applied while an actual background photo is active —
    // otherwise consumers should fall back to their own theme-aware styling.
    const foregroundTextClass = !hasBackground
      ? ""
      : isDarkBackground
        ? "text-text-light-05"
        : "text-text-dark-05";
    const foregroundMutedTextClass = !hasBackground
      ? ""
      : isDarkBackground
        ? "text-text-light-03"
        : "text-text-dark-03";
    const foregroundIconClass = !hasBackground
      ? ""
      : isDarkBackground
        ? "stroke-text-light-05"
        : "stroke-text-dark-05";
    const foregroundBorderClass = !hasBackground
      ? ""
      : isDarkBackground
        ? "border-text-light-03"
        : "border-text-dark-03";
    const foregroundTextStyle: React.CSSProperties = !hasBackground
      ? {}
      : {
          color: isDarkBackground
            ? "var(--text-light-05)"
            : "var(--text-dark-05)",
        };
    const foregroundMutedTextStyle: React.CSSProperties = !hasBackground
      ? {}
      : {
          color: isDarkBackground
            ? "var(--text-light-03)"
            : "var(--text-dark-03)",
        };
    const foregroundIconStyle: React.CSSProperties = !hasBackground
      ? {}
      : {
          stroke: isDarkBackground
            ? "var(--text-light-05)"
            : "var(--text-dark-05)",
        };
    const foregroundBorderStyle: React.CSSProperties = !hasBackground
      ? {}
      : {
          borderColor: isDarkBackground
            ? "var(--text-light-03)"
            : "var(--text-dark-03)",
        };

    return {
      appBackground,
      appBackgroundUrl,
      appBackgroundCanvas,
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
  }, [effectiveBackgroundId, colorMode, animateCanvas]);

  // Proactively warm up the browser image cache
  useEffect(() => {
    if (value.appBackgroundUrl) {
      preloadChatBackgroundImage(value.appBackgroundUrl);
    }
  }, [value.appBackgroundUrl]);

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
