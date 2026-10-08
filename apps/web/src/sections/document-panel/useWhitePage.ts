"use client";

import { useSyncExternalStore } from "react";

/**
 * How the document panel draws a document. The header button cycles the three,
 * so the sheet and its surroundings can be turned light independently:
 *
 * - `off`   — the app surface (dark in dark mode)
 * - `paper` — only the sheet (the text area) is a light page
 * - `page`  — the sheet *and* the whole reading area around it are a light page
 */
export type WhitePageMode = "off" | "paper" | "page";

const MODES: readonly WhitePageMode[] = ["off", "paper", "page"];

/**
 * "White page" preference for the document panel. Kept in `localStorage` rather
 * than the panel store: it is a presentation preference, not document state,
 * and it must survive a reload.
 */
export const WHITE_PAGE_STORAGE_KEY = "atlas.documentPanel.whitePage";

const listeners = new Set<() => void>();

function parseStored(value: string | null): WhitePageMode {
  if (MODES.includes(value as WhitePageMode)) return value as WhitePageMode;
  // Builds before the three-state cycle stored "1" for a light page.
  return value === "1" ? "page" : "off";
}

function readStored(): WhitePageMode {
  if (typeof window === "undefined") return "off";
  try {
    return parseStored(window.localStorage.getItem(WHITE_PAGE_STORAGE_KEY));
  } catch {
    return "off";
  }
}

/**
 * Read once per page load. The server has no `localStorage` and renders the
 * default; the panel itself is client-only state (`isOpen`), so nothing that
 * depends on this value is server-rendered and hydration cannot mismatch.
 */
let mode = readStored();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getWhitePageMode(): WhitePageMode {
  return mode;
}

export function setWhitePageMode(next: WhitePageMode): void {
  if (next === mode) return;
  mode = next;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(WHITE_PAGE_STORAGE_KEY, next);
    } catch {
      // Private mode or a full quota: the preference just does not persist.
    }
  }
  emit();
}

/** `off` → `paper` → `page` → `off`. */
export function cycleWhitePageMode(): WhitePageMode {
  const next = MODES[(MODES.indexOf(mode) + 1) % MODES.length]!;
  setWhitePageMode(next);
  return next;
}

/** The current mode and its setter (localStorage-backed). */
export function useWhitePage(): [WhitePageMode, (next: WhitePageMode) => void] {
  const value = useSyncExternalStore(
    subscribe,
    getWhitePageMode,
    () => "off" as WhitePageMode
  );
  return [value, setWhitePageMode];
}
