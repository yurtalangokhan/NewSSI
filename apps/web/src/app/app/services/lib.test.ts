import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { ReadonlyURLSearchParams } from "next/navigation";
import { buildChatUrl, processRawChatHistory } from "./lib";

describe("processRawChatHistory — forked (retried) flow-agent session", () => {
  it("builds a sibling tree: one user message with two assistant children", () => {
    // Shape returned by get_chat_session for a FlowAgent thread after a
    // retry forks a new branch — both answers persist as children of the
    // same user message (regression guard for the checkpoint_ns="" fix in
    // ThreadController.get_thread_state_history).
    const rawMessages = [
      {
        message_id: 1,
        message_type: "user",
        message: "rapor hazırla",
        parent_message: null,
        latest_child_message: 3,
        files: [],
      },
      {
        message_id: 2,
        message_type: "assistant",
        message: "ilk rapor",
        parent_message: 1,
        latest_child_message: null,
        files: [],
      },
      {
        message_id: 3,
        message_type: "assistant",
        message: "ikinci rapor",
        parent_message: 1,
        latest_child_message: null,
        files: [],
      },
    ] as any;
    const packets = [
      [
        {
          placement: { turn_index: 0, sub_turn_index: null },
          obj: {
            type: "graph_stage_start",
            stage_name: "ChatInput-x",
            timestamp: 1000,
          },
        },
      ],
      [
        {
          placement: { turn_index: 0, sub_turn_index: null },
          obj: {
            type: "graph_stage_start",
            stage_name: "ChatInput-x",
            timestamp: 5000,
          },
        },
      ],
    ] as any;

    const tree = processRawChatHistory(rawMessages, packets);

    const user = tree.get(1)!;
    expect(user.childrenNodeIds).toEqual([2, 3]);
    expect(user.latestChildNodeId).toBe(3);
    expect(tree.get(2)!.parentNodeId).toBe(1);
    expect(tree.get(3)!.parentNodeId).toBe(1);
    // packets map to assistants by order
    expect((tree.get(2)!.packets?.[0] as any).obj.timestamp).toBe(1000);
    expect((tree.get(3)!.packets?.[0] as any).obj.timestamp).toBe(5000);
  });
});

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
import { apiRequest } from "@/lib/api/http/browser";
import { createIdempotencyKey } from "@/lib/api/idempotency";
import { sendMessage } from "@/lib/api/domains/chat/api";

jest.mock("@/lib/api/http/browser", () => ({
  apiRequest: jest.fn(),
  parseJsonResponse: jest.fn(async (response: Response) => response.json()),
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
      .mocked(apiRequest)
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
    expect(apiRequest).toHaveBeenCalledWith(
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
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/chat/send-chat-message",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "stable-retry-key",
        }),
      })
    );
  });
});

describe("processRawChatHistory — message timestamps", () => {
  it("carries the backend's time_sent onto the message", () => {
    const rawMessages = [
      {
        message_id: 1,
        message_type: "user",
        message: "merhaba",
        parent_message: null,
        latest_child_message: 2,
        files: [],
        time_sent: "2026-08-12T13:06:00+00:00",
      },
      {
        message_id: 2,
        message_type: "assistant",
        message: "merhaba, nasıl yardımcı olabilirim?",
        parent_message: 1,
        latest_child_message: null,
        files: [],
        time_sent: "2026-08-12T13:06:04+00:00",
      },
    ] as any;

    const tree = processRawChatHistory(rawMessages, []);

    expect(tree.get(1)!.timeSent).toBe("2026-08-12T13:06:00+00:00");
    expect(tree.get(2)!.timeSent).toBe("2026-08-12T13:06:04+00:00");
  });

  it("leaves timeSent undefined when the backend could not stamp the message", () => {
    // The checkpoint-less fallback paths in chat_controller/session_controller
    // still return time_sent: null; those messages must render without a
    // timestamp rather than with a bogus one.
    const rawMessages = [
      {
        message_id: 1,
        message_type: "user",
        message: "merhaba",
        parent_message: null,
        latest_child_message: null,
        files: [],
        time_sent: null,
      },
    ] as any;

    expect(
      processRawChatHistory(rawMessages, []).get(1)!.timeSent
    ).toBeUndefined();
  });
});
