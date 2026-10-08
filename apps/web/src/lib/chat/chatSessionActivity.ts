import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";

interface ChatSessionActivityFields {
  id?: string | null;
  time_created?: string | null;
  time_updated?: string | null;
  last_message_at?: string | null;
}

interface ChatSessionsPage<TSession extends ChatSessionActivityFields> {
  sessions?: TSession[];
  has_more?: boolean;
  next_cursor?: {
    before_activity?: string | null;
    before_id?: string | null;
  } | null;
}

function hasLastMessageField(session: ChatSessionActivityFields): boolean {
  return Object.prototype.hasOwnProperty.call(session, "last_message_at");
}

function toTimestamp(value?: string | null): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function getChatSessionActivityTime(
  session: ChatSessionActivityFields
): string {
  if (hasLastMessageField(session)) {
    return session.last_message_at || session.time_created || "";
  }
  return session.time_updated || session.time_created || "";
}

export function getChatSessionFreshnessTime(
  session: ChatSessionActivityFields
): string {
  return (
    session.time_updated ||
    session.last_message_at ||
    session.time_created ||
    ""
  );
}

export function compareChatSessionsByActivityDesc<
  TSession extends ChatSessionActivityFields,
>(left: TSession, right: TSession): number {
  const diff =
    toTimestamp(getChatSessionActivityTime(right)) -
    toTimestamp(getChatSessionActivityTime(left));
  if (diff !== 0) {
    return diff;
  }
  return (right.id || "").localeCompare(left.id || "");
}

export function mergeChatSessionsByFreshness<
  TSession extends ChatSessionActivityFields,
>(sessions: TSession[]): TSession[] {
  const byId = new Map<string, TSession>();
  for (const session of sessions) {
    if (!session.id) {
      continue;
    }

    const existing = byId.get(session.id);
    if (!existing) {
      byId.set(session.id, session);
      continue;
    }

    const existingTime = toTimestamp(getChatSessionFreshnessTime(existing));
    const currentTime = toTimestamp(getChatSessionFreshnessTime(session));
    if (currentTime >= existingTime) {
      byId.set(session.id, session);
    }
  }
  return Array.from(byId.values()).sort(compareChatSessionsByActivityDesc);
}

export interface ChatSessionsPageFilters {
  /** Case-insensitive text matched against session names by the backend. */
  query?: string;
  /** Drop plain-model chats, keeping agent and flow sessions. */
  agentsOnly?: boolean;
}

export function getChatSessionsPageKey<
  TSession extends ChatSessionActivityFields,
>(
  pageIndex: number,
  previousPageData: ChatSessionsPage<TSession> | null,
  pageSize: number,
  filters: ChatSessionsPageFilters = {}
): string | null {
  if (previousPageData && !previousPageData.has_more) {
    return null;
  }

  const query = filters.query?.trim();
  const hasFilters = Boolean(query) || Boolean(filters.agentsOnly);

  if (pageIndex === 0 && !hasFilters) {
    return chatEndpoints.chatHistory(pageSize).browserPath;
  }

  const params = new URLSearchParams({
    page_size: pageSize.toString(),
  });
  if (query) {
    params.set("q", query);
  }
  if (filters.agentsOnly) {
    params.set("agents_only", "true");
  }

  if (pageIndex === 0) {
    return chatEndpoints.chatSessionHistoryQueryKey(params.toString())
      .browserPath;
  }

  const cursor = previousPageData?.next_cursor;
  if (cursor?.before_activity && cursor.before_id) {
    params.set("before_activity", cursor.before_activity);
    params.set("before_id", cursor.before_id);
    return chatEndpoints.chatSessionHistoryQueryKey(params.toString())
      .browserPath;
  }

  const lastSession =
    previousPageData?.sessions?.[previousPageData.sessions.length - 1];
  if (!lastSession?.id) {
    return null;
  }

  params.set("before_activity", getChatSessionActivityTime(lastSession));
  params.set("before_id", lastSession.id);
  return chatEndpoints.chatSessionHistoryQueryKey(params.toString())
    .browserPath;
}
