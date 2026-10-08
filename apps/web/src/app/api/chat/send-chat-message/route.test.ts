/**
 * This route only forwarded an incoming Authorization header (which
 * authenticatedFetch never sends -- it relies on the access_token cookie)
 * and never derived one from the cookie itself. agent-service is
 * bearer-token only and never reads cookies, so every chat message sent
 * through this route got a bare 401 -- the app's core feature was down.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { POST } from "./route";

describe("POST /api/chat/send-chat-message", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response("data: hello\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      })
    );

    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        method: "POST",
        body: JSON.stringify({ message: "hi" }),
        headers: { cookie: "access_token=real-session-token" },
      }
    );

    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
  });

  it("still prefers an explicit incoming Authorization header when present", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response("data: hello\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      })
    );

    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        method: "POST",
        body: JSON.stringify({ message: "hi" }),
        headers: {
          cookie: "access_token=cookie-token",
          authorization: "Bearer header-token",
        },
      }
    );

    await POST(request);

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer header-token"
    );
  });
});
