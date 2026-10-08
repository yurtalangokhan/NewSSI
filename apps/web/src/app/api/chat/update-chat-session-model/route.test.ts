import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { PUT } from "./route";

describe("PUT /api/chat/update-chat-session-model", () => {
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
      "http://localhost/api/chat/update-chat-session-model",
      {
        method: "PUT",
        body: JSON.stringify({ model: "x" }),
        headers: { cookie: "access_token=real-session-token" },
      }
    );

    await PUT(request);

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
  });
});
