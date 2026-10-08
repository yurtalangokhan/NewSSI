import { ChatSession } from "@/lib/api/domains/chat/types";
import { getChatSessionActivityTime } from "@/lib/chat/chatSessionActivity";
import { dayKey, formatDaySeparatorLabel } from "@/lib/dateUtils";

export interface ChatHistoryGroup {
  key: string;
  /** Day heading; null for sessions the backend could not date. */
  label: string | null;
  sessions: ChatSession[];
}

/**
 * Splits sessions, already in backend activity order, into runs that share a
 * calendar day, headed the way the chat transcript heads its days.
 *
 * A session without a usable timestamp joins the run already open rather than
 * starting one, so it never breaks the day it sits in.
 */
export function groupSessionsByDay(
  sessions: ChatSession[],
  locale: string,
  t: (key: string) => string,
  now: Date = new Date()
): ChatHistoryGroup[] {
  const groups: ChatHistoryGroup[] = [];
  let currentDay: string | null = null;

  for (const session of sessions) {
    const activity = getChatSessionActivityTime(session);
    const day = dayKey(activity);
    const open = groups[groups.length - 1];

    if (!day) {
      if (open) open.sessions.push(session);
      else groups.push({ key: "undated", label: null, sessions: [session] });
      continue;
    }

    if (day === currentDay && open) {
      open.sessions.push(session);
      continue;
    }

    currentDay = day;
    groups.push({
      // Indexed so a day the backend order revisits still gets a unique key.
      key: `${groups.length}-${day}`,
      label: formatDaySeparatorLabel(activity, locale, t, now),
      sessions: [session],
    });
  }

  return groups;
}
