import * as z from "zod";

/**
 * Environment flags are plain strings in `configs/.env`. Call sites used to
 * spell the comparison themselves — mostly `X?.toLowerCase() === "true"`,
 * occasionally the case-sensitive `X === "true"`. Both collapse into this one
 * coercion so a flag means the same thing everywhere it is read.
 *
 * A flag carries no fallback: it is declared with its value in
 * `packages/config-manager/src/config-manager/manager.py` and read from `configs/.env`.
 */
export function booleanFlag() {
  return z.string().transform((value) => value.trim().toLowerCase() === "true");
}

/**
 * An optional integration credential or URL. Blank becomes `undefined` so the
 * call site can branch on "not configured" — absence here means the integration
 * is off, not that a stand-in value applies.
 */
function trimmedString() {
  return z
    .string()
    .optional()
    .transform((value) => {
      const trimmed = value?.trim();
      return trimmed ? trimmed : undefined;
    });
}

/**
 * The auth modes the backend may report. Kept as literals rather than importing
 * `AuthType` from `lib/constants`, which reads this module — the import would
 * cycle. `constants.test.ts` asserts the two lists stay in step.
 */
export const AUTH_TYPES = [
  "basic",
  "google_oauth",
  "oidc",
  "saml",
  "cloud",
] as const;

/**
 * Server-only configuration. Reading any of these from a client component
 * throws, which is the point: several used to resolve to `undefined` in the
 * browser and silently take a fallback branch.
 */
export const serverSchema = {
  // Every service call is routed through Gateway; `./gateway` enforces that
  // these point at it rather than straight at a service host.
  GATEWAY_URL: z.url(),
  AGENT_SERVICE_URL: z.url(),
  USER_SERVICE_URL: z.url(),
  RAG_SERVICE_URL: z.url(),
  TOOLS_SERVICE_URL: z.url(),
  MCP_INTERNAL_URL: z.url(),

  // The public origin used to build redirect URLs. Required rather than
  // defaulted: the old `|| "http://localhost:3000"` and the production
  // "fall back to the request origin" branch both let a deployment run with no
  // configured domain, which is how a spoofed X-Forwarded-Host reaches a
  // redirect.
  WEB_DOMAIN: z.url(),

  AUTH_TYPE: z.enum(AUTH_TYPES),
  KEYCLOAK_ISSUER_URL: z.url().optional(),
  KEYCLOAK_CLIENT_ID: z.string().min(1),

  DEBUG_AUTH_COOKIE: trimmedString(),
  OVERRIDE_API_PRODUCTION: booleanFlag(),
  ATLAS_VERSION: z.string().min(1),

  CUSTOM_ANALYTICS_SECRET_KEY: trimmedString(),
  ENABLE_PAID_ENTERPRISE_EDITION_FEATURES: booleanFlag(),
};

/**
 * Variables Next.js inlines into the client bundle. Every key must carry the
 * `NEXT_PUBLIC_` prefix and appear literally in `experimental__runtimeEnv`,
 * or it reads as `undefined` in the browser.
 */
export const clientSchema = {
  NEXT_PUBLIC_SENTRY_DSN: trimmedString(),

  NEXT_PUBLIC_POSTHOG_KEY: trimmedString(),
  NEXT_PUBLIC_POSTHOG_HOST: z.url(),

  NEXT_PUBLIC_APP_NAME: z.string().min(1),
  NEXT_PUBLIC_APP_URL: z.string().min(1),
  NEXT_PUBLIC_APP_DOMAIN: z.string().min(1),
  NEXT_PUBLIC_SUPPORT_EMAIL: z.string().min(1),

  NEXT_PUBLIC_RECAPTCHA_SITE_KEY: trimmedString(),
  NEXT_PUBLIC_CUSTOM_REFRESH_URL: trimmedString(),

  NEXT_PUBLIC_CLOUD_ENABLED: booleanFlag(),
  NEXT_PUBLIC_GTM_ENABLED: booleanFlag(),
  NEXT_PUBLIC_ENABLE_STATS: booleanFlag(),
  NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES: booleanFlag(),
  NEXT_PUBLIC_DISABLE_LOGOUT: booleanFlag(),
  NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED: booleanFlag(),
  NEXT_PUBLIC_TEST_ENV: booleanFlag(),
  NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK: booleanFlag(),
  NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED: booleanFlag(),
};

/** Readable from both sides. */
export const sharedSchema = {
  NODE_ENV: z.enum(["development", "production", "test"]),
};
