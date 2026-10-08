import { Message } from "@/lib/api/domains/chat/types";
import { buildDaySeparators } from "./daySeparators";

const localIso = (month: number, day: number, hour = 12) =>
  new Date(2026, month - 1, day, hour, 0).toISOString();

const NOW = new Date(2026, 7, 12, 16, 6);

const t = (key: string) => key;

const msg = (nodeId: number, timeSent?: string): Message =>
  ({ nodeId, timeSent }) as Message;

const labels = (messages: Message[]) =>
  buildDaySeparators(messages, "tr", t, NOW);

describe("buildDaySeparators", () => {
  it("opens the transcript with the first message's day", () => {
    expect(labels([msg(1, localIso(3, 4))]).get(1)).toBe("4 Mart");
  });

  it("marks a message that starts a new day", () => {
    const separators = labels([
      msg(1, localIso(3, 4)),
      msg(2, localIso(3, 4, 18)),
      msg(3, localIso(3, 5)),
    ]);

    expect(separators.get(3)).toBe("5 Mart");
  });

  it("leaves messages that continue the current day unmarked", () => {
    const separators = labels([
      msg(1, localIso(3, 4, 9)),
      msg(2, localIso(3, 4, 18)),
    ]);

    expect(separators.has(2)).toBe(false);
  });

  it("names today and yesterday rather than dating them", () => {
    const separators = labels([
      msg(1, localIso(8, 11)),
      msg(2, localIso(8, 12)),
    ]);

    expect(separators.get(1)).toBe("dates.yesterday");
    expect(separators.get(2)).toBe("dates.today");
  });

  it("skips over an unstamped message without repeating the day", () => {
    // A history the backend could not stamp mixes with live messages that
    // carry a time. The unstamped one gets no separator of its own, and must
    // not make the next same-day message look like a new day.
    const separators = labels([
      msg(1, localIso(3, 4, 9)),
      msg(2, undefined),
      msg(3, localIso(3, 4, 18)),
    ]);

    expect(separators.has(2)).toBe(false);
    expect(separators.has(3)).toBe(false);
  });

  it("returns no separators at all when nothing is stamped", () => {
    expect(labels([msg(1), msg(2)]).size).toBe(0);
  });
});
