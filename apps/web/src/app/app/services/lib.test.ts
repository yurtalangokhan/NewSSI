import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { ReadonlyURLSearchParams } from "next/navigation";
import { buildChatUrl } from "./lib";

describe("buildChatUrl", () => {
  it("uses path routes for chat sessions and omits app state query params", () => {
    const existingSearchParams = new URLSearchParams({
      [SEARCH_PARAM_NAMES.PERSONA_ID]: "42",
      [SEARCH_PARAM_NAMES.PROJECT_ID]: "9",
      [SEARCH_PARAM_NAMES.USER_PROMPT]: "hello",
      keep: "this",
    }) as unknown as ReadonlyURLSearchParams;

    expect(buildChatUrl(existingSearchParams, "chat-1", 42, false, true)).toBe(
      "/app/chats/chat-1?skip-reload=true&keep=this"
    );
    expect(buildChatUrl(existingSearchParams, "chat-1", 42, false, false)).toBe(
      "/app/chats/chat-1?keep=this"
    );
  });

  it("keeps search route query behavior for search sessions", () => {
    expect(buildChatUrl(null, "search-1", null, true, false)).toBe(
      "/app?searchId=search-1"
    );
  });

  it("does not generate skip-reload query state for search sessions", () => {
    expect(buildChatUrl(null, "search-1", null, true, true)).toBe(
      "/app?searchId=search-1"
    );
  });
});
import { authenticatedFetch } from "@/lib/fetcher";
import { createIdempotencyKey } from "@/lib/api/idempotency";
import { sendMessage } from "@/app/app/services/lib";

jest.mock("@/lib/fetcher", () => ({
  authenticatedFetch: jest.fn(),
}));

jest.mock("@/lib/api/idempotency", () => ({
  createIdempotencyKey: jest.fn(),
  withIdempotencyKey: jest.fn((headers, key) => ({
    ...headers,
    "Idempotency-Key": key,
  })),
}));

jest.mock("@/lib/search/streamingUtils", () => ({
  handleSSEStream: jest.fn(async function* () {
    return;
  }),
}));

describe("sendMessage", () => {
  beforeEach(() => {
    jest.mocked(createIdempotencyKey).mockReturnValue("chat-operation-key");
    jest
      .mocked(authenticatedFetch)
      .mockResolvedValue(new Response(null, { status: 200 }));
  });

  it("sends a fresh idempotency key with each chat operation", async () => {
    for await (const _packet of sendMessage({
      message: "hello",
      parentMessageId: null,
      chatSessionId: "chat-1",
      filters: null,
    })) {
      // Consume the stream.
    }

    expect(createIdempotencyKey).toHaveBeenCalledTimes(1);
    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/chat/send-chat-message",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "Idempotency-Key": "chat-operation-key",
        }),
      })
    );
  });

  it("reuses a caller-provided idempotency key for retry of the same chat operation", async () => {
    for await (const _packet of sendMessage({
      message: "hello again",
      parentMessageId: null,
      chatSessionId: "chat-1",
      filters: null,
      idempotencyKey: "stable-retry-key",
    })) {
      // Consume the stream.
    }

    expect(createIdempotencyKey).not.toHaveBeenCalled();
    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/chat/send-chat-message",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "stable-retry-key",
        }),
      })
    );
  });
});
