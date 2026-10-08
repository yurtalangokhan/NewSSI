import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { DELETE } from "./route";

describe("DELETE /api/chat/remove-chat-message-feedback", () => {
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
      "http://localhost/api/chat/remove-chat-message-feedback",
      {
        method: "DELETE",
        body: JSON.stringify({ message_id: "m1" }),
        headers: { cookie: "access_token=real-session-token" },
      }
    );

    await DELETE(request);

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
  });
});
