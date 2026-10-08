import { AuthType } from "@/lib/constants";
import { env } from "@/lib/env";

/**
 * The web app's settings surface — the analogue of each backend service's
 * `core/config/settings.py`.
 *
 * The layering matches the Python services:
 *
 * - `lib/env/schema.ts` declares every variable and its type (pydantic fields)
 * - `lib/env` holds the validated values, built once at import (`Settings()`)
 * - this module is what application code reads (`appSettings.KEY`)
 *
 * There is no accessor layer above this module: routes read
 * `appSettings.AGENT_SERVICE_URL` directly, and tests override the module
 * rather than a set of getter functions.
 *
 * Members are getters rather than plain values. A server-only setting read from
 * a client component therefore still throws out of `lib/env`, naming the
 * variable, instead of silently resolving to `undefined` — which is what the
 * `SERVER_SIDE_ONLY__` prefixes below used to warn about by convention alone.
 */
export const appSettings = {
  // ---- Runtime ------------------------------------------------------------
  get NODE_ENV() {
    return env.NODE_ENV;
  },

  // ---- Service URLs (every one routed through Gateway) ---------------------
  get GATEWAY_URL() {
    return env.GATEWAY_URL;
  },
  get AGENT_SERVICE_URL() {
    return env.AGENT_SERVICE_URL;
  },
  get USER_SERVICE_URL() {
    return env.USER_SERVICE_URL;
  },
  get RAG_SERVICE_URL() {
    return env.RAG_SERVICE_URL;
  },
  get TOOLS_SERVICE_URL() {
    return env.TOOLS_SERVICE_URL;
  },
  get MCP_INTERNAL_URL() {
    return env.MCP_INTERNAL_URL;
  },

  /** The app's own public origin, used to build absolute URLs server-side. */
  get HOST_URL() {
    return env.WEB_DOMAIN;
  },

  // ---- Auth ---------------------------------------------------------------
  get SERVER_SIDE_ONLY__AUTH_TYPE(): AuthType {
    return env.AUTH_TYPE as AuthType;
  },
  get KEYCLOAK_ISSUER_URL() {
    return env.KEYCLOAK_ISSUER_URL;
  },
  get KEYCLOAK_CLIENT_ID() {
    return env.KEYCLOAK_CLIENT_ID;
  },
  get LOGOUT_DISABLED() {
    return env.NEXT_PUBLIC_DISABLE_LOGOUT;
  },
  get NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED() {
    return (
      env.NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED && !env.NEXT_PUBLIC_CLOUD_ENABLED
    );
  },
  get NEXT_PUBLIC_CUSTOM_REFRESH_URL() {
    return env.NEXT_PUBLIC_CUSTOM_REFRESH_URL;
  },
  get NEXT_PUBLIC_RECAPTCHA_SITE_KEY() {
    return env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY;
  },

  // ---- Development aids ---------------------------------------------------
  /** Injects a session cookie when developing against a remote backend. */
  get DEBUG_AUTH_COOKIE() {
    return env.DEBUG_AUTH_COOKIE;
  },
  /** Opens the generic /api/* proxy outside development. */
  get OVERRIDE_API_PRODUCTION() {
    return env.OVERRIDE_API_PRODUCTION;
  },
  get NEXT_PUBLIC_TEST_ENV() {
    return env.NEXT_PUBLIC_TEST_ENV;
  },

  // ---- Branding -----------------------------------------------------------
  get APP_NAME() {
    return env.NEXT_PUBLIC_APP_NAME;
  },
  get APP_URL() {
    return env.NEXT_PUBLIC_APP_URL;
  },
  get APP_SUPPORT_EMAIL() {
    return env.NEXT_PUBLIC_SUPPORT_EMAIL;
  },
  /** Tenant sign-up domain suffix. */
  get NEXT_PUBLIC_APP_DOMAIN() {
    return env.NEXT_PUBLIC_APP_DOMAIN;
  },
  get NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED() {
    return env.NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED;
  },
  get ATLAS_VERSION() {
    return env.ATLAS_VERSION;
  },

  // ---- Analytics ----------------------------------------------------------
  get NEXT_PUBLIC_SENTRY_DSN() {
    return env.NEXT_PUBLIC_SENTRY_DSN;
  },
  get NEXT_PUBLIC_POSTHOG_KEY() {
    return env.NEXT_PUBLIC_POSTHOG_KEY;
  },
  get NEXT_PUBLIC_POSTHOG_HOST() {
    return env.NEXT_PUBLIC_POSTHOG_HOST;
  },
  get NEXT_PUBLIC_ENABLE_STATS() {
    return env.NEXT_PUBLIC_ENABLE_STATS;
  },
  get GTM_ENABLED() {
    return env.NEXT_PUBLIC_GTM_ENABLED;
  },
  /** Whether a custom analytics script may be fetched for this deployment. */
  get CUSTOM_ANALYTICS_ENABLED() {
    return env.CUSTOM_ANALYTICS_SECRET_KEY !== undefined;
  },

  // ---- Edition and feature flags ------------------------------------------
  get SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED() {
    return env.ENABLE_PAID_ENTERPRISE_EDITION_FEATURES;
  },
  get NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES() {
    return env.NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES;
  },
  get NEXT_PUBLIC_CLOUD_ENABLED() {
    return env.NEXT_PUBLIC_CLOUD_ENABLED;
  },
  get NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK() {
    return env.NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK;
  },
} as const;
