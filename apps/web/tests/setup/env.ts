/**
 * Baseline environment for the test run.
 *
 * `src/lib/env` validates at module-evaluation time, so every variable it
 * requires must exist before any test file's imports are evaluated. This runs
 * as a `setupFiles` entry, which Jest executes ahead of both the test framework
 * and the module graph.
 *
 * These are deterministic fixtures, not a copy of `configs/.env`: a test that
 * cares about a particular value mocks `@/lib/env` or `@/lib/env.server` rather
 * than reaching for the real environment. Service URLs are Gateway-routed
 * because `src/lib/env/gateway.ts` rejects anything that is not.
 *
 * Optional integrations (Sentry, PostHog keys, custom analytics, the debug auth
 * cookie, the captcha key) are deliberately absent — their absence is what "not configured"
 * means.
 */
const GATEWAY_URL = "http://localhost:8000";

const BASELINE_ENV: Record<string, string> = {
  GATEWAY_URL,
  AGENT_SERVICE_URL: `${GATEWAY_URL}/agent-service`,
  USER_SERVICE_URL: `${GATEWAY_URL}/user-service`,
  RAG_SERVICE_URL: `${GATEWAY_URL}/rag-service`,
  TOOLS_SERVICE_URL: `${GATEWAY_URL}/tools-service/mcp`,
  MCP_INTERNAL_URL: `${GATEWAY_URL}/internal/tools-service/mcp`,

  WEB_DOMAIN: "http://localhost:3000",
  AUTH_TYPE: "basic",
  KEYCLOAK_CLIENT_ID: "agenticai-web",
  OVERRIDE_API_PRODUCTION: "false",
  ATLAS_VERSION: "dev",
  ENABLE_PAID_ENTERPRISE_EDITION_FEATURES: "false",

  NEXT_PUBLIC_POSTHOG_HOST: "https://us.posthog.com",
  NEXT_PUBLIC_APP_NAME: "TURKSAT ATLAS",
  NEXT_PUBLIC_APP_URL: "/",
  NEXT_PUBLIC_APP_DOMAIN: "atlas.app",
  NEXT_PUBLIC_SUPPORT_EMAIL: "support@example.com",

  NEXT_PUBLIC_CLOUD_ENABLED: "false",
  NEXT_PUBLIC_GTM_ENABLED: "false",
  NEXT_PUBLIC_ENABLE_STATS: "false",
  NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES: "false",
  NEXT_PUBLIC_DISABLE_LOGOUT: "false",
  NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED: "false",
  NEXT_PUBLIC_TEST_ENV: "false",
  NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK: "false",
  NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED: "false",
};

for (const [key, value] of Object.entries(BASELINE_ENV)) {
  process.env[key] = value;
}

export {};
