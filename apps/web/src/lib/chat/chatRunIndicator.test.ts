import { getChatRunIndicator } from "@/lib/chat/chatRunIndicator";

const base = {
  has_active_run: false,
  last_message_at: null,
  last_accessed_at: null,
};

describe("getChatRunIndicator", () => {
  it("prefers the live run state over the unread heuristic", () => {
    expect(
      getChatRunIndicator({
        ...base,
        has_active_run: true,
        last_message_at: "2026-10-01T10:00:00Z",
        last_accessed_at: "2026-10-01T09:00:00Z",
      })
    ).toBe("running");
  });

  it("marks an answer newer than the last open as unread", () => {
    expect(
      getChatRunIndicator({
        ...base,
        last_message_at: "2026-10-01T10:00:00Z",
        last_accessed_at: "2026-10-01T09:00:00Z",
      })
    ).toBe("unread");
  });

  it("treats a never-opened chat with an answer as unread", () => {
    expect(
      getChatRunIndicator({ ...base, last_message_at: "2026-10-01T10:00:00Z" })
    ).toBe("unread");
  });

  it("stays quiet when the last open is newer than the answer", () => {
    expect(
      getChatRunIndicator({
        ...base,
        last_message_at: "2026-10-01T09:00:00Z",
        last_accessed_at: "2026-10-01T10:00:00Z",
      })
    ).toBeNull();
  });

  it("stays quiet for an untouched chat", () => {
    expect(getChatRunIndicator(base)).toBeNull();
  });

  it("ignores timestamps it cannot parse", () => {
    expect(
      getChatRunIndicator({ ...base, last_message_at: "not-a-date" })
    ).toBeNull();
  });
});
