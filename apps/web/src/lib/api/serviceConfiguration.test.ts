import { readFileSync } from "fs";
import { resolve } from "path";

jest.mock("@sentry/nextjs", () => ({
  withSentryConfig: (config: unknown) => config,
}));

describe("service configuration boundaries", () => {
  const original = { ...process.env };

  it("keeps service resolution behind typed settings and gateway routing", () => {
    const env = readFileSync(
      resolve(process.cwd(), "src/lib/env/index.ts"),
      "utf8"
    );
    const settings = readFileSync(
      resolve(process.cwd(), "src/lib/settings.ts"),
      "utf8"
    );
    const transport = readFileSync(
      resolve(process.cwd(), "src/lib/api/http/server.ts"),
      "utf8"
    );
    const mcp = readFileSync(
      resolve(process.cwd(), "src/app/mcp/[[...path]]/route.ts"),
      "utf8"
    );
    expect(`${env}\n${settings}`).not.toMatch(
      /\bINTERNAL_URL\b|MCP_SERVER_URL/
    );
    expect(transport).toContain('from "@/lib/settings"');
    expect(transport).toContain('from "@/lib/api/gatewayRouting"');
    expect(transport).not.toContain("process.env");
    expect(mcp).not.toMatch(/getMcpInternalUrl|\/internal\//);
  });
  afterEach(() => {
    process.env = { ...original };
  });

  it("does not invent a backend for Next.js rewrites", async () => {
    delete process.env.AGENT_SERVICE_URL;
    process.env.INTERNAL_URL = "https://obsolete.example";
    const config = require("../../../next.config.js");
    await expect(config.rewrites()).rejects.toThrow("AGENT_SERVICE_URL");
  });

  it("uses the configured service for existing backend rewrites", async () => {
    process.env.AGENT_SERVICE_URL = "https://configured.example/agent/";
    const config = require("../../../next.config.js");
    const routes = await config.rewrites();
    expect(
      routes.fallback.find(
        (route: { source: string }) => route.source === "/openapi.json"
      ).destination
    ).toBe("https://configured.example/agent/openapi.json");
  });

  it("builds registration navigation from the configured web domain", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/app/auth/create-account/page.tsx"),
      "utf8"
    );
    expect(source).not.toContain("REGISTRATION_URL");
    expect(source).toContain("settings?.webDomain");
    expect(source).toContain("/register`");
  });
});
