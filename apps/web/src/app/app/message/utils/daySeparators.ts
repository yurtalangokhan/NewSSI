import { Message } from "@/lib/api/domains/chat/types";
import { dayKey, formatDaySeparatorLabel } from "@/lib/dateUtils";

/**
 * Decides where a transcript needs a day heading, and what it should read.
 *
 * Returns node id -> heading for each message that opens a calendar day; a
 * message continuing the day already on screen gets no entry. An unstamped
 * message is passed over entirely — it neither gets a heading nor closes the
 * running day, so a stamped message after it is still judged against the last
 * day actually seen rather than appearing to start a fresh one.
 */
export function buildDaySeparators(
  messages: Pick<Message, "nodeId" | "timeSent">[],
  locale: string,
  t: (key: string) => string,
  now: Date = new Date()
): Map<number, string> {
  const separators = new Map<number, string>();
  let currentDay: string | null = null;

  for (const message of messages) {
    const key = dayKey(message.timeSent);
    if (!key || key === currentDay) continue;

    const label = formatDaySeparatorLabel(message.timeSent, locale, t, now);
    if (!label) continue;

    separators.set(message.nodeId, label);
    currentDay = key;
  }

  return separators;
}
