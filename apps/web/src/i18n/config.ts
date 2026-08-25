import i18next, { i18n as I18nInstance } from "i18next";
import { initReactI18next } from "react-i18next";

import enCommon from "./locales/en";
import trCommon from "./locales/tr";
import {
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  SupportedLanguage,
} from "./locales";

export * from "./locales";

const resources = {
  en: { common: enCommon },
  tr: { common: trCommon },
};

const sharedInitOptions = {
  resources,
  defaultNS: "common",
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: SUPPORTED_LANGUAGES.map((lang) => lang.code),
  interpolation: {
    escapeValue: false,
  },
  react: {
    useSuspense: false,
  },
};

/**
 * Creates a dedicated i18next instance for the React tree (mounted once per
 * `I18nProvider`). This is intentionally NOT the shared default-exported
 * singleton below: the root layout renders per-request, and mutating a
 * module-level singleton's language during that render would be a race
 * condition across concurrent requests from users with different locales.
 * The instance's initial language comes from the server-resolved locale, so
 * the very first paint already renders in the right language (no flash).
 *
 * Client-only: this file imports `react-i18next`, which crashes if pulled
 * into a Server Component's module graph. Server-side code must use
 * `@/i18n/server` (plain `i18next`, no React) instead.
 */
export function createI18nInstance(
  initialLanguage: SupportedLanguage = DEFAULT_LANGUAGE
): I18nInstance {
  const instance = i18next.createInstance();
  instance.use(initReactI18next).init({
    ...sharedInitOptions,
    lng: initialLanguage,
  });
  return instance;
}

/**
 * Shared browser-only instance used by plain utility modules (toasts, error
 * formatters, etc.) that call `i18n.t(...)` outside of the React tree and
 * therefore can't read from `I18nextProvider` context. It only ever runs in
 * the browser, so it's safe as a singleton (no cross-request sharing). Its
 * language is kept in sync with the user's choice via `syncDefaultInstanceLanguage`.
 */
const i18n = i18next.createInstance();
i18n.use(initReactI18next).init({
  ...sharedInitOptions,
  lng: DEFAULT_LANGUAGE,
});

export function syncDefaultInstanceLanguage(language: SupportedLanguage) {
  void i18n.changeLanguage(language);
}

export default i18n;
