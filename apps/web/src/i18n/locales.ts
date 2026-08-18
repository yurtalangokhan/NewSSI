/**
 * Locale constants with zero dependency on `react-i18next`. Next.js Server
 * Components crash on module-eval if anything in their import graph pulls in
 * `react-i18next` (it calls `React.createContext()` as an import side
 * effect). Server-side code (locale resolution, server-rendered
 * translations) must import from here instead of `./config`, which is
 * client-only.
 */

export const I18N_LANGUAGE_COOKIE_NAME = "NEXT_LOCALE";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "tr", label: "Türkçe" },
] as const;

export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]["code"];

export const DEFAULT_LANGUAGE: SupportedLanguage = "en";

export function isSupportedLanguage(
  value: string | null | undefined
): value is SupportedLanguage {
  return SUPPORTED_LANGUAGES.some((lang) => lang.code === value);
}
