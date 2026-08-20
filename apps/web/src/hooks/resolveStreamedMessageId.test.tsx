import { resolveStreamedMessageId } from "@/hooks/useChatController";

describe("resolveStreamedMessageId", () => {
  it("prefers the id streamed mid-response when present", () => {
    expect(resolveStreamedMessageId(42, 99)).toBe(42);
  });

  it("falls back to the final packet's id when the backend never streams a reserved id", () => {
    // The backend currently never sends reserved_assistant_message_id /
    // user_message_id mid-stream, so this is the path that actually fires
    // in production — without it, freshly streamed message nodes keep their
    // temporary negative nodeId forever and later operations that need a
    // real messageId (e.g. switching back to this sibling) fail.
    expect(resolveStreamedMessageId(null, 99)).toBe(99);
  });

  it("returns undefined when neither source has an id yet", () => {
    expect(resolveStreamedMessageId(null, undefined)).toBeUndefined();
    expect(resolveStreamedMessageId(null, null)).toBeUndefined();
  });
});
