"use client";

import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES } from "@/i18n/config";
import LineItem from "@/refresh-components/buttons/LineItem";
import { SvgGlobe } from "@opal/icons";

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  const toggleLanguage = () => {
    const nextLang = i18n.language === "tr" ? "en" : "tr";
    i18n.changeLanguage(nextLang);
  };

  const nextLang =
    SUPPORTED_LANGUAGES.find((l) => l.code !== i18n.language) ??
    SUPPORTED_LANGUAGES[0];

  return (
    <LineItem icon={SvgGlobe} onClick={toggleLanguage}>
      {t("language.switchTo", { language: nextLang.label })}
    </LineItem>
  );
}
