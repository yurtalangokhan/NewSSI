import { backendRequest } from "@/lib/api/http/server";
import { fetchBackendChatSessionSS, fetchSharedChatSS } from "../server";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/api/server-context", () => ({
  getServerRequestHeaders: jest.fn().mockResolvedValue({ cookie: "session=1" }),
}));

it("preserves normal and shared chat-session server requests", async () => {
  jest.mocked(backendRequest).mockImplementation(async () =>
    Response.json({
      statusCode: 200,
      message: null,
      data: { id: "chat-1" },
      error: null,
    })
  );

  await fetchBackendChatSessionSS("chat-1");
  await fetchSharedChatSS("chat-1");

  expect(backendRequest).toHaveBeenNthCalledWith(
    1,
    expect.objectContaining({
      service: "agent",
      path: "/api/v1/chat/sessions/chat-1",
    })
  );
  expect(backendRequest).toHaveBeenNthCalledWith(
    2,
    expect.objectContaining({ query: { is_shared: "True" } })
  );
});
