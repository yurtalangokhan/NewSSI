import {
  DEFAULT_LANGUAGE,
  I18N_LANGUAGE_COOKIE_NAME,
  isSupportedLanguage,
  SupportedLanguage,
} from "@/i18n/locales";
import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

let currentLanguage: SupportedLanguage | null = null;

function languageFromCookie(): SupportedLanguage {
  if (typeof document === "undefined") {
    return DEFAULT_LANGUAGE;
  }

  const match = document.cookie.match(
    new RegExp(`(?:^|; )${I18N_LANGUAGE_COOKIE_NAME}=([^;]*)`)
  );
  const cookieLanguage = match?.[1] ? decodeURIComponent(match[1]) : null;
  return isSupportedLanguage(cookieLanguage)
    ? cookieLanguage
    : DEFAULT_LANGUAGE;
}

export function getClientLanguage(): SupportedLanguage {
  return currentLanguage ?? languageFromCookie();
}

export function setClientLanguage(language: string): void {
  if (isSupportedLanguage(language)) {
    currentLanguage = language;
  }
}

export function getClientAuthErrorMessage(): string {
  return getClientLanguage() === "tr"
    ? tr.common.fetchAuthError
    : en.common.fetchAuthError;
}
