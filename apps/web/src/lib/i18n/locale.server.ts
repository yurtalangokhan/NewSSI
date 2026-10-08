import { cookies, headers } from "next/headers";
import {
  DEFAULT_LANGUAGE,
  I18N_LANGUAGE_COOKIE_NAME,
  SUPPORTED_LANGUAGES,
  SupportedLanguage,
  isSupportedLanguage,
} from "@/i18n/locales";

function parseAcceptLanguage(header: string | null): SupportedLanguage | null {
  if (!header) {
    return null;
  }

  const supportedCodes = SUPPORTED_LANGUAGES.map((lang) => lang.code);

  const preferred = header
    .split(",")
    .map((part) => part.trim().split(";")[0]?.toLowerCase().split("-")[0])
    .find((code) => supportedCodes.includes(code as SupportedLanguage));

  return isSupportedLanguage(preferred) ? preferred : null;
}

/**
 * Resolves the locale to render with on the server: an explicit cookie
 * (set once the user picks a language) takes priority, falling back to the
 * browser's `Accept-Language` header for first-time visitors, and finally
 * the app default. Resolving this before render (rather than after mount,
 * client-side) is what avoids the default-language flash on first paint.
 */
export async function resolveLocaleSS(): Promise<SupportedLanguage> {
  const requestCookies = await cookies();
  const cookieLocale = requestCookies.get(I18N_LANGUAGE_COOKIE_NAME)?.value;
  if (isSupportedLanguage(cookieLocale)) {
    return cookieLocale;
  }

  const requestHeaders = await headers();
  const acceptLanguageLocale = parseAcceptLanguage(
    requestHeaders.get("accept-language")
  );

  return acceptLanguageLocale ?? DEFAULT_LANGUAGE;
}
