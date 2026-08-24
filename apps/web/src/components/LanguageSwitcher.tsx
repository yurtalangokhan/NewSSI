"use client";

import { useTranslation } from "react-i18next";
import { I18N_LANGUAGE_COOKIE_NAME, SUPPORTED_LANGUAGES } from "@/i18n/config";
import { SvgGlobe } from "@opal/icons";

const LANGUAGE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

interface LanguageSwitcherProps {
  variant?: "button" | "menu";
}

export function LanguageSwitcher({ variant = "menu" }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation();

  const toggleLanguage = () => {
    const nextLang = i18n.language === "tr" ? "en" : "tr";
    // Cookie makes the choice visible to the server on the next request, so
    // the page can render in the right language from the very first paint.
    document.cookie = `${I18N_LANGUAGE_COOKIE_NAME}=${nextLang}; path=/; max-age=${LANGUAGE_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
    i18n.changeLanguage(nextLang);
  };

  const nextLang =
    SUPPORTED_LANGUAGES.find((l) => l.code !== i18n.language) ??
    SUPPORTED_LANGUAGES[0];

  if (variant === "button") {
    return (
      <button
        onClick={toggleLanguage}
        className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-background-tint-01/40 hover:bg-background-tint-01/60 border border-border transition-colors text-sm font-medium text-white/80 hover:text-white"
        title={t("language.switchTo", { language: nextLang.label })}
      >
        <SvgGlobe className="w-4 h-4" />
        <span>{nextLang.code.toUpperCase()}</span>
      </button>
    );
  }

  // Menu variant (original)
  const LineItem = require("@/refresh-components/buttons/LineItem").default;
  return (
    <LineItem icon={SvgGlobe} onClick={toggleLanguage}>
      {t("language.switchTo", { language: nextLang.label })}
    </LineItem>
  );
}
