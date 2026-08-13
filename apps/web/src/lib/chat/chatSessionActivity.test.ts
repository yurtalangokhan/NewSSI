import {
  compareChatSessionsByActivityDesc,
  getChatSessionActivityTime,
  getChatSessionFreshnessTime,
  getChatSessionsPageKey,
  mergeChatSessionsByFreshness,
} from "@/lib/chat/chatSessionActivity";

function session(overrides: Record<string, unknown>): Record<string, any> {
  return {
    id: "session",
    time_created: "2026-08-07T09:00:00Z",
    time_updated: "2026-08-07T12:00:00Z",
    ...overrides,
  };
}

describe("chat session activity helpers", () => {
  it("uses last_message_at when present and falls back to created time for explicit nulls", () => {
    expect(
      getChatSessionActivityTime(
        session({ last_message_at: "2026-08-07T11:00:00Z" })
      )
    ).toBe("2026-08-07T11:00:00Z");

    expect(getChatSessionActivityTime(session({ last_message_at: null }))).toBe(
      "2026-08-07T09:00:00Z"
    );
  });

  it("uses updated time only for legacy records where last_message_at is absent", () => {
    expect(getChatSessionActivityTime(session({}))).toBe(
      "2026-08-07T12:00:00Z"
    );
  });

  it("uses freshness instead of activity when deduplicating session copies", () => {
    const staleNameWithNewerMessage = session({
      id: "same",
      name: "Old name",
      time_updated: "2026-08-07T10:00:00Z",
      last_message_at: "2026-08-07T15:00:00Z",
    });
    const freshMetadata = session({
      id: "same",
      name: "Fresh name",
      time_updated: "2026-08-07T14:00:00Z",
      last_message_at: "2026-08-07T11:00:00Z",
    });

    expect(
      mergeChatSessionsByFreshness([
        staleNameWithNewerMessage,
        freshMetadata,
      ])[0]?.name
    ).toBe("Fresh name");
    expect(getChatSessionFreshnessTime(freshMetadata)).toBe(
      "2026-08-07T14:00:00Z"
    );
  });

  it("orders sessions by message activity with deterministic id fallback", () => {
    const ordered = [
      session({ id: "b", last_message_at: null }),
      session({ id: "a", last_message_at: "2026-08-07T14:00:00Z" }),
      session({ id: "c", last_message_at: "2026-08-07T14:00:00Z" }),
    ].sort(compareChatSessionsByActivityDesc);

    expect(ordered.map((item) => item.id)).toEqual(["c", "a", "b"]);
  });

  it("builds chat list keys from backend activity cursors", () => {
    expect(getChatSessionsPageKey(0, null, 50)).toBe(
      "/api/chat/get-user-chat-sessions?page_size=50"
    );

    expect(
      getChatSessionsPageKey(
        1,
        {
          sessions: [session({ id: "older" })],
          has_more: true,
          next_cursor: {
            before_activity: "2026-08-07T10:00:00Z",
            before_id: "older",
          },
        },
        50
      )
    ).toBe(
      "/api/chat/get-user-chat-sessions?page_size=50&before_activity=2026-08-07T10%3A00%3A00Z&before_id=older"
    );
  });
});
