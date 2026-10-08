import { appSettings } from "@/lib/settings";

export const APP_TAGLINE = "Your AI platform for work";

export function getAppName(applicationName?: string | null) {
  return applicationName?.trim() || appSettings.APP_NAME;
}

export function buildAppFooterMarkdown(webVersion?: string | null) {
  return `[${appSettings.APP_NAME} ${webVersion || "dev"}](${
    appSettings.APP_URL
  })`;
}
