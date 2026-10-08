import Cookies from "js-cookie";
import {
  CHAT_BACKGROUND_COOKIE_NAME,
  CHAT_BACKGROUND_NONE,
  getBackgroundById,
  isCanvasBackground,
} from "@/lib/constants/chatBackgrounds";

/**
 * Reads the chat background ID stored in the client cookie.
 */
export function getChatBackgroundCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const value = Cookies.get(CHAT_BACKGROUND_COOKIE_NAME);
  if (!value || value === CHAT_BACKGROUND_NONE) {
    return null;
  }
  return value;
}

/**
 * Persists the selected chat background ID in a 1-year cookie so that
 * subsequent page loads can immediately identify and preload it on the server (SSR).
 */
export function setChatBackgroundCookie(backgroundId: string) {
  if (typeof document === "undefined") {
    return;
  }
  if (!backgroundId || backgroundId === CHAT_BACKGROUND_NONE) {
    clearChatBackgroundCookie();
    return;
  }
  Cookies.set(CHAT_BACKGROUND_COOKIE_NAME, backgroundId, {
    expires: 365,
    path: "/",
    sameSite: "lax",
  });
}

/**
 * Removes the chat background cookie when user selects 'None'.
 */
export function clearChatBackgroundCookie() {
  if (typeof document === "undefined") {
    return;
  }
  Cookies.remove(CHAT_BACKGROUND_COOKIE_NAME, { path: "/" });
}

/**
 * Proactively fetches the background image into browser memory cache.
 * Accepts either an option ID (e.g. "mountains") or a direct image URL (e.g. "/chat-backgrounds/mountains.jpg").
 */
export function preloadChatBackgroundImage(
  backgroundIdOrSrc: string | null | undefined
) {
  if (
    typeof window === "undefined" ||
    !backgroundIdOrSrc ||
    backgroundIdOrSrc === CHAT_BACKGROUND_NONE
  ) {
    return;
  }

  const option = getBackgroundById(backgroundIdOrSrc);
  // Canvas-kind options have no image to fetch.
  if (option && isCanvasBackground(option)) {
    return;
  }
  const src =
    option && option.src !== CHAT_BACKGROUND_NONE
      ? option.src
      : backgroundIdOrSrc.startsWith("/")
        ? backgroundIdOrSrc
        : null;

  if (src && src !== CHAT_BACKGROUND_NONE) {
    const img = new Image();
    img.src = src;
  }
}
