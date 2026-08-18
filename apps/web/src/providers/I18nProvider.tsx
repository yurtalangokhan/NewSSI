"use client";

import { useEffect, useState } from "react";
import { I18nextProvider } from "react-i18next";
import {
  createI18nInstance,
  syncDefaultInstanceLanguage,
  SupportedLanguage,
} from "@/i18n/config";

export default function I18nProvider({
  children,
  initialLocale,
}: {
  children: React.ReactNode;
  initialLocale: SupportedLanguage;
}) {
  // Created once, seeded with the server-resolved locale, so the first
  // render (SSR and hydration alike) already renders in the right language.
  const [instance] = useState(() => createI18nInstance(initialLocale));

  // Keeps the browser-only default instance (used by non-component utility
  // modules calling `i18n.t()` directly) in sync with the tree's language.
  useEffect(() => {
    syncDefaultInstanceLanguage(instance.language as SupportedLanguage);
    instance.on("languageChanged", syncDefaultInstanceLanguage);
    return () => {
      instance.off("languageChanged", syncDefaultInstanceLanguage);
    };
  }, [instance]);

  return <I18nextProvider i18n={instance}>{children}</I18nextProvider>;
}
