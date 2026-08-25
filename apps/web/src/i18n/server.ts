import i18next from "i18next";

import enCommon from "./locales/en";
import trCommon from "./locales/tr";
import {
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  SupportedLanguage,
} from "./locales";

/**
 * Plain `i18next` instance (no `react-i18next`) for translating strings
 * inside Server Components. `react-i18next` calls `React.createContext()` as
 * an import side effect, which crashes Next.js if it ends up in a Server
 * Component's module graph — so this deliberately avoids it.
 *
 * `lng` is always passed per-call rather than via `changeLanguage()`: this
 * instance is a module-level singleton shared across concurrent requests,
 * and mutating its language would race between users with different locales.
 */
const serverI18n = i18next.createInstance();
serverI18n.init({
  resources: {
    en: { common: enCommon },
    tr: { common: trCommon },
  },
  lng: DEFAULT_LANGUAGE,
  defaultNS: "common",
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: SUPPORTED_LANGUAGES.map((lang) => lang.code),
  interpolation: {
    escapeValue: false,
  },
});

export function tServer(
  key: string,
  options: Record<string, unknown> & { lng: SupportedLanguage }
): string {
  return serverI18n.t(key, options) as string;
}
