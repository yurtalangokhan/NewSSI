jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { POST } from "./route";
import { NextRequest } from "next/server";

function request(headers: HeadersInit = {}) {
  return new NextRequest(
    "http://localhost/api/chat/stop-chat-session/session-1",
    {
      method: "POST",
      headers,
    }
  );
}

describe("POST /api/chat/stop-chat-session/[chatSessionId]", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    fetchSpy.mockResolvedValueOnce(new Response("{}", { status: 200 }));

    await POST(request({ cookie: "access_token=real-session-token" }), {
      params: Promise.resolve({ chatSessionId: "session-1" }),
    });

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
  });
});
