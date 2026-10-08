import { requireEnv } from "./requireEnv";

/**
 * Spec: `next.config.js` runs as plain Node before the app is bundled, so it
 * cannot import the typed `src/lib/env` schema (zod + t3-env, TypeScript) --
 * `noStrayEnvReads.test.ts` only scans `.tsx?` files under `src/` for exactly
 * this reason, tacitly accepting next.config.js as the one place outside that
 * module allowed to read `process.env` directly.
 *
 * That is also why it used to fall back to a hardcoded default
 * (`AGENT_SERVICE_URL || "http://localhost:8080"`) instead of failing fast
 * the way every other required URL does in `schema.ts`: it had no shared
 * helper to fail fast with. `requireEnv` is that helper -- a plain CommonJS
 * function next.config.js can `require()` without any TypeScript tooling.
 */
describe("requireEnv", () => {
  it("returns the value when it is a non-empty string", () => {
    expect(
      requireEnv("AGENT_SERVICE_URL", "http://gateway:8000/agent-service")
    ).toBe("http://gateway:8000/agent-service");
  });

  it("trims surrounding whitespace", () => {
    expect(requireEnv("AGENT_SERVICE_URL", "  http://gateway:8000  ")).toBe(
      "http://gateway:8000"
    );
  });

  it("throws when the value is undefined", () => {
    expect(() => requireEnv("AGENT_SERVICE_URL", undefined)).toThrow(
      /AGENT_SERVICE_URL/
    );
  });

  it("throws when the value is an empty string", () => {
    expect(() => requireEnv("AGENT_SERVICE_URL", "")).toThrow(
      /AGENT_SERVICE_URL/
    );
  });

  it("throws when the value is whitespace only", () => {
    // A blank `configs/.env` line (`AGENT_SERVICE_URL=`) must not silently
    // count as configured -- matching the schema's own
    // `emptyStringAsUndefined` handling for every other required var.
    expect(() => requireEnv("AGENT_SERVICE_URL", "   ")).toThrow(
      /AGENT_SERVICE_URL/
    );
  });

  it("names the variable in the error so a missing config fails loudly, not silently", () => {
    // The bug this replaces: an unset AGENT_SERVICE_URL silently became
    // "http://localhost:8080" and every request routed nowhere real, with no
    // error naming what was missing.
    expect(() => requireEnv("NEXT_PUBLIC_POSTHOG_HOST", undefined)).toThrow(
      "NEXT_PUBLIC_POSTHOG_HOST is required but was not set. Configure it in configs/.env."
    );
  });
});
