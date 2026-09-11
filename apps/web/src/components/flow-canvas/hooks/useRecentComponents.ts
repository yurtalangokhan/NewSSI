/**
 * Recently-used components, pinned above the categories. This is our own
 * addition, not a Langflow port — Langflow's sidebar has no recents list
 * (design spec brief for Task 25). Persisted to localStorage so it
 * survives a reload; capped at MAX_RECENTS, most-recent-first.
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "flow-canvas:recent-components";
const MAX_RECENTS = 8;
const RECENTS_EVENT = "flow-canvas:recents-updated";

function readStoredRecents(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((v) => typeof v === "string")
      : [];
  } catch {
    return [];
  }
}

export function recordRecentComponent(componentType: string) {
  if (typeof window === "undefined" || !componentType) return;
  try {
    const current = readStoredRecents();
    const withoutDuplicate = current.filter((t) => t !== componentType);
    const next = [componentType, ...withoutDuplicate].slice(0, MAX_RECENTS);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(RECENTS_EVENT));
  } catch {}
}

export function useRecentComponents() {
  const [recents, setRecents] = useState<string[]>(() => readStoredRecents());

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleUpdate = () => {
      setRecents(readStoredRecents());
    };
    window.addEventListener(RECENTS_EVENT, handleUpdate);
    window.addEventListener("storage", handleUpdate);
    return () => {
      window.removeEventListener(RECENTS_EVENT, handleUpdate);
      window.removeEventListener("storage", handleUpdate);
    };
  }, []);

  const recordUsage = useCallback((componentType: string) => {
    recordRecentComponent(componentType);
  }, []);

  return { recents, recordUsage };
}
