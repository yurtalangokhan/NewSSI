"use client";

import { useCallback, useState } from "react";
import {
  loadRecentSearches,
  pushRecentSearch,
  recentSearchesStorageKey,
  saveRecentSearches,
} from "@/sections/knowledge-search/model/recentSearches";

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

interface RecentSearchesSnapshot {
  /** The storage key this history was loaded for; `null` when signed out. */
  key: string | null;
  recent: string[];
}

function loadSnapshot(key: string | null): RecentSearchesSnapshot {
  return { key, recent: loadRecentSearches(browserStorage(), key) };
}

/** The signed-in user's recent knowledge searches in this browser. */
export function useRecentSearches(userId: string | null) {
  const key = recentSearchesStorageKey(userId);
  const [snapshot, setSnapshot] = useState(() => loadSnapshot(key));

  // Another user's history replaces this one during render (React's
  // "adjust state on prop change" pattern), so no frame shows the previous
  // user's searches and no effect has to re-sync afterwards.
  let current = snapshot;
  if (snapshot.key !== key) {
    current = loadSnapshot(key);
    setSnapshot(current);
  }
  const { recent } = current;

  const add = useCallback(
    (query: string) => {
      const next = pushRecentSearch(recent, query);
      saveRecentSearches(next, browserStorage(), key);
      setSnapshot({ key, recent: next });
    },
    [key, recent]
  );

  const clear = useCallback(() => {
    saveRecentSearches([], browserStorage(), key);
    setSnapshot({ key, recent: [] });
  }, [key]);

  return { recent, add, clear };
}
