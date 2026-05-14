import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enCommon from "./locales/en";
import trCommon from "./locales/tr";

export const I18N_LANGUAGE_STORAGE_KEY = "i18n-language";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "tr", label: "Türkçe" },
] as const;

export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]["code"];

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: enCommon },
      tr: { common: trCommon },
    },
    lng: "en",
    defaultNS: "common",
    fallbackLng: "en",
    supportedLngs: ["en", "tr"],
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
    },
  });

export default i18n;
