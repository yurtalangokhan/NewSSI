import { defineConfig } from "i18next-cli";

export default defineConfig({
  locales: ["en", "tr"],
  extract: {
    input: ["src/**/*.{ts,tsx}"],
    ignore: [
      "src/i18n/locales/**",
      "**/*.test.{ts,tsx}",
      "**/*.stories.{ts,tsx}",
    ],
    output: "src/i18n/locales/{{language}}.ts",
    outputFormat: "ts",
    defaultNS: "common",
    primaryLanguage: "en",
    secondaryLanguages: ["tr"],
    // Keep this false until extract output has been reviewed against the
    // current hand-maintained files - the static extractor can miss
    // dynamically-built keys and would otherwise delete them.
    removeUnusedKeys: false,
    sort: true,
  },
  types: {
    input: ["src/i18n/locales/en.ts"],
    output: "src/i18n/i18next-resources.d.ts",
  },
});
