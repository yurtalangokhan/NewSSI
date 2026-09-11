jest.mock("@/lib/env.server", () => ({
  getInternalUrl: () => "http://kong",
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
      "http://kong/agent-service/api/v1/chat/rename-chat-session",
      {
        method: "PUT",
        body,
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-access-token",
          Cookie: "access_token=test-cookie",
          "Idempotency-Key": "rename-session-1",
        },
      }
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ name: "New name" });
  });

  it("keeps cookie-only authentication without inventing bearer credentials", async () => {
    const fetchMock = jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const response = await PUT(request({ Cookie: "access_token=test-cookie" }));

    const headers = new Headers(fetchMock.mock.calls[0]![1]?.headers);
    expect(headers.get("cookie")).toBe("access_token=test-cookie");
    expect(headers.has("authorization")).toBe(false);
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
