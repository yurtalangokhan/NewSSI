import { Message } from "@/lib/api/domains/chat/types";
import { upsertMessages } from "./messageTree";

const message = (overrides: Partial<Message> = {}): Message => ({
  nodeId: 1,
  message: "merhaba",
  type: "user",
  files: [],
  toolCall: null,
  parentNodeId: null,
  packets: [],
  ...overrides,
});

describe("upsertMessages — message timestamps", () => {
  it("stamps a message that arrives without a timestamp", () => {
    // Messages built during a live send (useChatController) carry no
    // time_sent — the backend only stamps them once they are in a
    // checkpoint, which is after the transcript has already rendered them.
    const before = Date.now();
    const tree = upsertMessages(new Map(), [message()]);
    const after = Date.now();

    const stamped = Date.parse(tree.get(1)!.timeSent!);
    expect(stamped).toBeGreaterThanOrEqual(before);
    expect(stamped).toBeLessThanOrEqual(after);
  });

  it("keeps the original stamp when the same node is upserted again", () => {
    // Streaming re-upserts the agent node on every packet. Re-stamping each
    // time would make the displayed clock crawl forward while the answer is
    // still being written.
    const first = upsertMessages(new Map(), [
      message({ nodeId: 2, type: "assistant" }),
    ]);
    const originalStamp = first.get(2)!.timeSent;
    expect(Number.isNaN(Date.parse(originalStamp!))).toBe(false);

    const second = upsertMessages(first, [
      message({ nodeId: 2, type: "assistant", message: "daha uzun cevap" }),
    ]);

    expect(second.get(2)!.timeSent).toBe(originalStamp);
    expect(second.get(2)!.message).toBe("daha uzun cevap");
  });

  it("prefers a timestamp the caller supplied over both the stored and a fresh one", () => {
    const first = upsertMessages(new Map(), [message({ nodeId: 3 })]);

    const second = upsertMessages(first, [
      message({ nodeId: 3, timeSent: "2026-08-12T13:06:00+00:00" }),
    ]);

    expect(second.get(3)!.timeSent).toBe("2026-08-12T13:06:00+00:00");
  });
});
