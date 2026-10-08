import React, { type ReactElement } from "react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import type { SupportedLanguage } from "@/i18n/locales";
import { render } from "./test-utils";

/**
 * test-utils render (SWR and Radix Tooltip providers) plus a real i18n
 * instance, so assertions use the shipped en/tr copy. `rerender` keeps the
 * i18n provider.
 */
export function renderWithI18n(
  ui: ReactElement,
  locale: SupportedLanguage = "en"
) {
  const i18n = createI18nInstance(locale);
  const wrap = (node: ReactElement) => (
    <I18nextProvider i18n={i18n}>{node}</I18nextProvider>
  );
  const result = render(wrap(ui));
  return {
    ...result,
    rerender: (next: ReactElement) => result.rerender(wrap(next)),
  };
}
