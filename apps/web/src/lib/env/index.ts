import { createEnv } from "@t3-oss/env-nextjs";

import { assertGatewayRouted } from "./gateway";
import { clientSchema, serverSchema, sharedSchema } from "./schema";

/**
 * The single place this app reads `process.env`.
 *
 * Validation runs when this module is first evaluated, so a missing or
 * malformed variable fails at boot with a message naming it, rather than as an
 * undefined value taking a fallback branch somewhere downstream. Reading a
 * server-only key from a client component throws for the same reason.
 *
 * Every client and shared key is listed literally in `experimental__runtimeEnv`
 * below. Next.js only inlines the ones it can see spelled out, so a key added
 * to `clientSchema` without a line here reads as `undefined` in the browser.
 */
export const env = createEnv({
  server: serverSchema,
  client: clientSchema,
  shared: sharedSchema,
  experimental__runtimeEnv: {
    NODE_ENV: process.env.NODE_ENV,

    NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN,

    NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
    NEXT_PUBLIC_POSTHOG_HOST: process.env.NEXT_PUBLIC_POSTHOG_HOST,

    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
    NEXT_PUBLIC_APP_DOMAIN: process.env.NEXT_PUBLIC_APP_DOMAIN,
    NEXT_PUBLIC_SUPPORT_EMAIL: process.env.NEXT_PUBLIC_SUPPORT_EMAIL,

    NEXT_PUBLIC_RECAPTCHA_SITE_KEY: process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY,
    NEXT_PUBLIC_CUSTOM_REFRESH_URL: process.env.NEXT_PUBLIC_CUSTOM_REFRESH_URL,

    NEXT_PUBLIC_CLOUD_ENABLED: process.env.NEXT_PUBLIC_CLOUD_ENABLED,
    NEXT_PUBLIC_GTM_ENABLED: process.env.NEXT_PUBLIC_GTM_ENABLED,
    NEXT_PUBLIC_ENABLE_STATS: process.env.NEXT_PUBLIC_ENABLE_STATS,
    NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES:
      process.env.NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES,
    NEXT_PUBLIC_DISABLE_LOGOUT: process.env.NEXT_PUBLIC_DISABLE_LOGOUT,
    NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED:
      process.env.NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED,
    NEXT_PUBLIC_TEST_ENV: process.env.NEXT_PUBLIC_TEST_ENV,
    NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK:
      process.env.NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK,
    NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED:
      process.env.NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED,
  },
  emptyStringAsUndefined: true,
});

/**
 * Service URLs are shaped correctly by the schema but must also be *routed*
 * correctly. Run that cross-field check once, on the server, right after the
 * schema passes — on the client these keys are not readable at all.
 */
if (typeof window === "undefined") {
  const gateway = env.GATEWAY_URL;

  for (const name of [
    "AGENT_SERVICE_URL",
    "USER_SERVICE_URL",
    "RAG_SERVICE_URL",
    "TOOLS_SERVICE_URL",
    "MCP_INTERNAL_URL",
  ] as const) {
    assertGatewayRouted(name, env[name], gateway);
  }
}
