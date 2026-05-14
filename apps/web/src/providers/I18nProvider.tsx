"use client";

import { useEffect, useState } from "react";
import i18n, {
  I18N_LANGUAGE_STORAGE_KEY,
  SUPPORTED_LANGUAGES,
  SupportedLanguage,
} from "@/i18n/config";

export default function I18nProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const storedLanguage = window.localStorage.getItem(
      I18N_LANGUAGE_STORAGE_KEY
    ) as SupportedLanguage | null;
    const navigatorLanguage = window.navigator.language
      .toLowerCase()
      .split("-")[0] as SupportedLanguage;
    const supportedCodes = SUPPORTED_LANGUAGES.map((lang) => lang.code);

    const nextLanguage =
      storedLanguage && supportedCodes.includes(storedLanguage)
        ? storedLanguage
        : supportedCodes.includes(navigatorLanguage)
          ? navigatorLanguage
          : "en";

    void i18n.changeLanguage(nextLanguage);

    setMounted(true);
  }, []);

  if (!mounted) {
    return <>{children}</>;
  }

  return <>{children}</>;
}
