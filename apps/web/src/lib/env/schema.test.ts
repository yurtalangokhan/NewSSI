import * as z from "zod";

import {
  booleanFlag,
  clientSchema,
  serverSchema,
  sharedSchema,
} from "./schema";

describe("booleanFlag", () => {
  const parse = (value: string) =>
    z.object({ FLAG: booleanFlag() }).parse({ FLAG: value }).FLAG;

  it("reads 'true' as true regardless of case or surrounding space", () => {
    expect(parse("true")).toBe(true);
    expect(parse("TRUE")).toBe(true);
    expect(parse("  True  ")).toBe(true);
  });

  it("reads any other value as false", () => {
    expect(parse("false")).toBe(false);
    expect(parse("1")).toBe(false);
    expect(parse("yes")).toBe(false);
  });

  it("requires the flag to be declared rather than defaulting it", () => {
    expect(z.object({ FLAG: booleanFlag() }).safeParse({}).success).toBe(false);
  });
});

describe("serverSchema", () => {
  const complete = {
    GATEWAY_URL: "http://localhost:8000",
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
    USER_SERVICE_URL: "http://localhost:8000/user-service",
    RAG_SERVICE_URL: "http://localhost:8000/rag-service",
    TOOLS_SERVICE_URL: "http://localhost:8000/tools-service/mcp",
    MCP_INTERNAL_URL: "http://localhost:8000/internal/tools-service/mcp",
    WEB_DOMAIN: "http://localhost:3000",
    AUTH_TYPE: "oidc",
    KEYCLOAK_CLIENT_ID: "agenticai-web",
    OVERRIDE_API_PRODUCTION: "false",
    ATLAS_VERSION: "dev",
    ENABLE_PAID_ENTERPRISE_EDITION_FEATURES: "false",
  };

  it("accepts a complete set of service URLs", () => {
    expect(() => z.object(serverSchema).parse(complete)).not.toThrow();
  });

  it("names the variable when a required service URL is missing", () => {
    const { GATEWAY_URL: _omitted, ...withoutGateway } = complete;
    const result = z.object(serverSchema).safeParse(withoutGateway);

    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(["GATEWAY_URL"]);
  });

  it("rejects a service URL that is not absolute", () => {
    const result = z
      .object(serverSchema)
      .safeParse({ ...complete, AGENT_SERVICE_URL: "/agent-service" });

    expect(result.success).toBe(false);
  });

  it.each([
    "WEB_DOMAIN",
    "AUTH_TYPE",
    "KEYCLOAK_CLIENT_ID",
    "ATLAS_VERSION",
  ] as const)(
    "requires %s from the environment rather than substituting a value",
    (key) => {
      const { [key]: _omitted, ...without } = complete;
      const result = z.object(serverSchema).safeParse(without);

      expect(result.success).toBe(false);
      expect(result.error?.issues[0]?.path).toEqual([key]);
    }
  );

  it("rejects an AUTH_TYPE the app cannot act on", () => {
    const result = z
      .object(serverSchema)
      .safeParse({ ...complete, AUTH_TYPE: "ldap" });

    expect(result.success).toBe(false);
  });
});

describe("clientSchema", () => {
  it("requires every key to carry the NEXT_PUBLIC_ prefix", () => {
    const unprefixed = Object.keys(clientSchema).filter(
      (key) => !key.startsWith("NEXT_PUBLIC_")
    );

    expect(unprefixed).toEqual([]);
  });

  const completeClient = {
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

  it("carries no substitute value for a branding key the environment omits", () => {
    const { NEXT_PUBLIC_APP_NAME: _omitted, ...without } = completeClient;

    expect(z.object(clientSchema).safeParse(without).success).toBe(false);
  });

  it("leaves unconfigured integrations undefined rather than substituting", () => {
    const parsed = z.object(clientSchema).parse(completeClient);

    expect(parsed.NEXT_PUBLIC_SENTRY_DSN).toBeUndefined();
    expect(parsed.NEXT_PUBLIC_POSTHOG_KEY).toBeUndefined();
    expect(parsed.NEXT_PUBLIC_CUSTOM_REFRESH_URL).toBeUndefined();
    expect(parsed.NEXT_PUBLIC_RECAPTCHA_SITE_KEY).toBeUndefined();
  });
});

describe("sharedSchema", () => {
  it("constrains NODE_ENV to the three Next.js modes", () => {
    expect(z.object(sharedSchema).parse({ NODE_ENV: "test" }).NODE_ENV).toBe(
      "test"
    );
    expect(
      z.object(sharedSchema).safeParse({ NODE_ENV: "staging" }).success
    ).toBe(false);
  });
});
