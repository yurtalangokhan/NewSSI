import {
  BackendChatSession,
  ChatSessionSharedStatus,
  toChatSession,
} from "@/app/app/interfaces";

function backendSession(
  overrides: Partial<BackendChatSession> = {}
): BackendChatSession {
  return {
    chat_session_id: "chat-1",
    description: "Legacy chat",
    persona_id: 0,
    persona_name: "Assistant",
    messages: [],
    time_created: "2026-08-07T09:00:00Z",
    time_updated: "2026-08-07T12:00:00Z",
    shared_status: ChatSessionSharedStatus.Private,
    current_temperature_override: null,
    owner_name: null,
    packets: [],
    ...overrides,
  };
}

describe("toChatSession", () => {
  it("preserves legacy omission of last_message_at", () => {
    const session = toChatSession(backendSession());

    expect(Object.hasOwn(session, "last_message_at")).toBe(false);
    expect(Object.hasOwn(session, "last_accessed_at")).toBe(false);
  });

  it("preserves explicit activity timestamp fields", () => {
    const session = toChatSession(
      backendSession({
        last_message_at: null,
        last_accessed_at: "2026-08-07T13:00:00Z",
      })
    );

    expect(Object.hasOwn(session, "last_message_at")).toBe(true);
    expect(session.last_message_at).toBeNull();
    expect(session.last_accessed_at).toBe("2026-08-07T13:00:00Z");
  });
});
