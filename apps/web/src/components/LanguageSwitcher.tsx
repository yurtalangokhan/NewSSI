"use client";

import { useTranslation } from "react-i18next";
import { I18N_LANGUAGE_STORAGE_KEY, SUPPORTED_LANGUAGES } from "@/i18n/config";
import { SvgGlobe } from "@opal/icons";

interface LanguageSwitcherProps {
  variant?: "button" | "menu";
}

export function LanguageSwitcher({ variant = "menu" }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation();

  const toggleLanguage = () => {
    const nextLang = i18n.language === "tr" ? "en" : "tr";
    window.localStorage.setItem(I18N_LANGUAGE_STORAGE_KEY, nextLang);
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
