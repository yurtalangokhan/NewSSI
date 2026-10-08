jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://apisix/agent-service",
  },
}));

import { PUT } from "../route";

const body = JSON.stringify({ chat_session_id: "session-1", name: "New name" });

function request(headers: HeadersInit = {}) {
  return new Request("http://web.test/api/chat/rename-chat-session", {
    method: "PUT",
    headers,
    body,
  });
}

describe("rename chat session proxy", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("forwards incoming bearer credentials with cookies and idempotency", async () => {
    const fetchMock = jest.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ name: "New name" }), {
        headers: { "Content-Type": "application/json" },
      })
    );

    const response = await PUT(
      request({
        Authorization: "Bearer test-access-token",
        Cookie: "access_token=test-cookie",
        "Idempotency-Key": "rename-session-1",
      })
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://apisix/agent-service/api/v1/chat/rename-chat-session",
      {
        method: "PUT",
        body,
        headers: expect.any(Headers),
      }
    );
    const headers = new Headers(fetchMock.mock.calls[0]![1]?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("authorization")).toBe("Bearer test-access-token");
    expect(headers.get("cookie")).toBe("access_token=test-cookie");
    expect(headers.get("idempotency-key")).toBe("rename-session-1");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ name: "New name" });
  });

  it("derives a bearer credential from a cookie-only request", async () => {
    // agent-service is bearer-token only and never reads cookies (see
    // AuthService._extract_auth_token), so a cookie-only request that
    // never got an Authorization header derived from it always got a
    // bare 401 -- this used to be asserted as the intended behavior.
    const fetchMock = jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const response = await PUT(request({ Cookie: "access_token=test-cookie" }));

    const headers = new Headers(fetchMock.mock.calls[0]![1]?.headers);
    expect(headers.get("cookie")).toBe("access_token=test-cookie");
    expect(headers.get("authorization")).toBe("Bearer test-cookie");
    expect(response.status).toBe(204);
  });

  it.each([401, 403, 409])(
    "preserves backend %i errors and replay markers",
    async (status) => {
      const error = { detail: "Backend rejection" };
      const fetchMock = jest.spyOn(global, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify(error), {
          status,
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Replayed": "true",
          },
        })
      );

      const response = await PUT(request());

      const headers = new Headers(fetchMock.mock.calls[0]![1]?.headers);
      expect(headers.has("authorization")).toBe(false);
      expect(headers.has("cookie")).toBe(false);
      expect(response.status).toBe(status);
      expect(response.headers.get("Idempotency-Replayed")).toBe("true");
      expect(await response.json()).toEqual(error);
    }
  );
});
