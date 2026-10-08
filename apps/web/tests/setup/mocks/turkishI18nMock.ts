/**
 * react-i18next stand-in that resolves keys from the real Turkish locale,
 * with `_one`/`_other` plurals and `{{name}}` interpolation, so tests assert
 * the text a reader actually sees.
 */
import tr from "@/i18n/locales/tr";

type Options = Record<string, unknown> & {
  count?: number;
  defaultValue?: string;
};

function lookup(key: string): string | undefined {
  let node: unknown = tr;
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

export function translate(key: string, options?: string | Options): string {
  if (typeof options === "string") return lookup(key) ?? options;
  const plural =
    options?.count !== undefined
      ? lookup(`${key}_${options.count === 1 ? "one" : "other"}`)
      : undefined;
  const template = plural ?? lookup(key) ?? options?.defaultValue ?? key;
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
    String(options?.[name] ?? "")
  );
}

export const turkishI18nMock = {
  useTranslation: () => ({ t: translate, i18n: { language: "tr" } }),
  // src/i18n/config registers the React binding at import time.
  initReactI18next: { type: "3rdParty", init: () => undefined },
};
