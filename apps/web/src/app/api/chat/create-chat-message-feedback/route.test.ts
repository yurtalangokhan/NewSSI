import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { POST } from "./route";

describe("POST /api/chat/create-chat-message-feedback", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    fetchSpy.mockResolvedValueOnce(new Response("{}", { status: 200 }));

    const request = new NextRequest(
      "http://localhost/api/chat/create-chat-message-feedback",
      {
        method: "POST",
        body: JSON.stringify({ message_id: "m1", positive: true }),
        headers: { cookie: "access_token=real-session-token" },
      }
    );

    await POST(request);

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
  });
});
