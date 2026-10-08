import { cookies } from "next/headers";
import {
  CHAT_BACKGROUND_COOKIE_NAME,
  CHAT_BACKGROUND_NONE,
  getBackgroundById,
  ChatBackgroundOption,
} from "@/lib/constants/chatBackgrounds";
import { User } from "@/lib/types";

export interface AppBackgroundMetadata {
  backgroundId: string | null;
  backgroundOption: ChatBackgroundOption | undefined;
}

/**
 * Resolves the active chat background metadata on the server side (SSR).
 * Prioritizes the authenticated user's saved preferences if available,
 * falling back to the 1-year client cookie so the server knows the background
 * immediately even before auth session verification finishes.
 */
export async function fetchAppBackgroundMetadata(
  user?: User | null
): Promise<AppBackgroundMetadata> {
  let backgroundId = user?.preferences?.chat_background ?? null;
  if (backgroundId === CHAT_BACKGROUND_NONE) {
    backgroundId = null;
  }

  if (!backgroundId) {
    try {
      const requestCookies = await cookies();
      const cookieBackground = requestCookies.get(CHAT_BACKGROUND_COOKIE_NAME)
        ?.value;
      if (cookieBackground && cookieBackground !== CHAT_BACKGROUND_NONE) {
        backgroundId = cookieBackground;
      }
    } catch {
      // In non-request contexts or mock environments, cookies() might throw.
    }
  }

  const backgroundOption = getBackgroundById(backgroundId);

  return {
    backgroundId,
    backgroundOption,
  };
}
