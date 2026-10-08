/**
 * Recent knowledge searches, kept per browser. Storage can be missing or
 * blocked (private windows, strict cookie settings), so every access is
 * guarded and the page works without it.
 */

const STORAGE_KEY_PREFIX = "atlas.knowledgeSearch.recent";
export const MAX_RECENT_SEARCHES = 6;

type SearchStorage = Pick<Storage, "getItem" | "setItem">;

/** Per-user storage key, so a shared browser keeps histories apart. */
export function recentSearchesStorageKey(userId: string | null): string | null {
  return userId ? `${STORAGE_KEY_PREFIX}.${userId}` : null;
}

/** The newest query first, without case-insensitive duplicates, capped. */
export function pushRecentSearch(
  recent: readonly string[],
  query: string
): string[] {
  const trimmed = query.trim();
  if (!trimmed) return [...recent];
  const folded = trimmed.toLocaleLowerCase();
  return [
    trimmed,
    ...recent.filter((item) => item.toLocaleLowerCase() !== folded),
  ].slice(0, MAX_RECENT_SEARCHES);
}

export function loadRecentSearches(
  storage: SearchStorage | null,
  key: string | null
): string[] {
  if (!storage || !key) return [];
  try {
    const parsed: unknown = JSON.parse(storage.getItem(key) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === "string")
      .slice(0, MAX_RECENT_SEARCHES);
  } catch {
    return [];
  }
}

export function saveRecentSearches(
  recent: readonly string[],
  storage: SearchStorage | null,
  key: string | null
): void {
  if (!storage || !key) return;
  try {
    storage.setItem(key, JSON.stringify(recent));
  } catch {
    // Storage is a convenience; a blocked write only loses history.
  }
}
