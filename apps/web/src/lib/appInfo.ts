const DEFAULT_APP_NAME = "TURKSAT ATLAS";
const DEFAULT_APP_TAGLINE = "Your AI platform for work";
const DEFAULT_APP_URL = "/";
const DEFAULT_SUPPORT_EMAIL = "support@example.com";

export const APP_NAME =
  process.env.NEXT_PUBLIC_APP_NAME?.trim() || DEFAULT_APP_NAME;

export const APP_TAGLINE = DEFAULT_APP_TAGLINE;

export const APP_URL =
  process.env.NEXT_PUBLIC_APP_URL?.trim() || DEFAULT_APP_URL;

export const APP_SUPPORT_EMAIL =
  process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim() || DEFAULT_SUPPORT_EMAIL;

export function getAppName(applicationName?: string | null) {
  return applicationName?.trim() || APP_NAME;
}

export function buildAppFooterMarkdown(webVersion?: string | null) {
  return `[${APP_NAME} ${webVersion || "dev"}](${APP_URL})`;
}
