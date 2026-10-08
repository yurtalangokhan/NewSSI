/**
 * Same missing-Authorization bug as the other hand-rolled proxy routes:
 * this dev-only fallback cloned the browser's incoming headers verbatim,
 * so a request that only carried the access_token cookie (the normal
 * case) never got an Authorization header when its default path fell
 * through to agent-service, which is bearer-token only.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/api/routeBackendUrl", () => ({
  getBackendUrl: () =>
    new URL("http://localhost:8000/agent-service/api/v1/some-path"),
}));

// The route gates itself on NODE_ENV, which the validated env object
// captures once at import — so the module is overridden rather than
// process.env mutated per test.
jest.mock("@/lib/env", () => {
  const actual = jest.requireActual("@/lib/env");
  return { env: { ...actual.env, NODE_ENV: "development" } };
});

import { GET } from "./route";

describe("GET /api/[...path] (dev-only fallback)", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    const request = new NextRequest("http://localhost/api/some-path", {
      headers: { cookie: "access_token=real-session-token" },
    });

    await GET(request, { params: Promise.resolve({ path: ["some-path"] }) });

    const [, init] = fetchSpy.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer real-session-token");
  });
});
