jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { GET } from "./route";
import { NextRequest } from "next/server";

function request(headers: HeadersInit = {}) {
  return new NextRequest(
    "http://localhost/api/chat/available-context-tokens/session-1",
    { headers }
  );
}

describe("GET /api/chat/available-context-tokens/[sessionId]", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ max_tokens: 1, selected_tokens: 1 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );

    await GET(request({ cookie: "access_token=real-session-token" }), {
      params: Promise.resolve({ sessionId: "session-1" }),
    });

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
  });
});
