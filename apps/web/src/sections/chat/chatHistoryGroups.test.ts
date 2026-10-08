import { ChatSession } from "@/lib/api/domains/chat/types";
import { groupSessionsByDay } from "./chatHistoryGroups";

const NOW = new Date(2026, 7, 12, 16, 6);
const t = (key: string) => key;

const localIso = (month: number, day: number, hour = 12) =>
  new Date(2026, month - 1, day, hour, 0).toISOString();

const session = (id: string, lastMessageAt?: string): ChatSession =>
  ({ id, last_message_at: lastMessageAt }) as ChatSession;

const group = (sessions: ChatSession[]) =>
  groupSessionsByDay(sessions, "tr", t, NOW);

describe("groupSessionsByDay", () => {
  it("groups consecutive sessions of one day under a single label", () => {
    const groups = group([
      session("a", localIso(3, 4, 18)),
      session("b", localIso(3, 4, 9)),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]!.label).toBe("4 Mart");
    expect(groups[0]!.sessions.map((s) => s.id)).toEqual(["a", "b"]);
  });

  it("starts a new group when the day changes, keeping backend order", () => {
    const groups = group([
      session("a", localIso(8, 12)),
      session("b", localIso(8, 11)),
      session("c", localIso(3, 4)),
    ]);

    expect(groups.map((g) => g.label)).toEqual([
      "dates.today",
      "dates.yesterday",
      "4 Mart",
    ]);
  });

  it("puts a session with no timestamp into the running group", () => {
    const groups = group([
      session("a", localIso(3, 4)),
      session("b", undefined),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]!.sessions.map((s) => s.id)).toEqual(["a", "b"]);
  });

  it("leaves a leading unstamped session in a group without a label", () => {
    const groups = group([
      session("a", undefined),
      session("b", localIso(3, 4)),
    ]);

    expect(groups[0]!.label).toBeNull();
    expect(groups[0]!.sessions.map((s) => s.id)).toEqual(["a"]);
    expect(groups[1]!.label).toBe("4 Mart");
  });

  it("returns no groups for no sessions", () => {
    expect(group([])).toEqual([]);
  });
});
