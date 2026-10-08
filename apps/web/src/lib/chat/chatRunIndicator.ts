import { ChatSession } from "@/lib/api/domains/chat/types";

/** The subset of a chat row the sidebar run indicator needs. */
export type ChatRunIndicatorFields = Pick<
  ChatSession,
  "has_active_run" | "last_message_at" | "last_accessed_at"
>;

export type ChatRunIndicator = "running" | "unread" | null;

function toMillis(value?: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * What the sidebar shows for one chat row.
 *
 * - `running`: a run is still producing the answer. This is server-owned
 *   truth (`has_active_run`), so it holds even after the browser left the page.
 * - `unread`: the newest answer arrived after the chat was last opened.
 * - `null`: nothing to show.
 */
export function getChatRunIndicator(
  session: ChatRunIndicatorFields
): ChatRunIndicator {
  if (session.has_active_run) return "running";

  const answeredAt = toMillis(session.last_message_at);
  if (answeredAt === null) return null;

  const openedAt = toMillis(session.last_accessed_at);
  return openedAt === null || answeredAt > openedAt ? "unread" : null;
}
