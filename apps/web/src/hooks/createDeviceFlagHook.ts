"use client";

import { useCallback, useSyncExternalStore } from "react";

const DISABLED = "off";

interface DeviceFlagConfig {
  storageKey: string;
  changeEvent: string;
}

/**
 * Builds a hook for a boolean display preference that belongs to this device
 * (and browser profile) rather than to the account, so it lives in
 * `localStorage` and not in the account's synced settings.
 *
 * The flag defaults to `true`, including on the server, and only the disabled
 * state is stored. It stays in step across components and tabs. When storage
 * is blocked (private mode, site data disabled) the choice is kept in memory
 * for the life of the page so the switch still works.
 */
export default function createDeviceFlagHook({
  storageKey,
  changeEvent,
}: DeviceFlagConfig): () => [boolean, (enabled: boolean) => void] {
  let sessionValue = true;

  function read(): boolean {
    try {
      return window.localStorage.getItem(storageKey) !== DISABLED;
    } catch {
      return sessionValue;
    }
  }

  function write(enabled: boolean): void {
    sessionValue = enabled;
    try {
      if (enabled) {
        window.localStorage.removeItem(storageKey);
      } else {
        window.localStorage.setItem(storageKey, DISABLED);
      }
    } catch {
      // Storage is unavailable; `sessionValue` carries the choice.
    }
    window.dispatchEvent(new Event(changeEvent));
  }

  function subscribe(onChange: () => void): () => void {
    window.addEventListener("storage", onChange);
    window.addEventListener(changeEvent, onChange);
    return () => {
      window.removeEventListener("storage", onChange);
      window.removeEventListener(changeEvent, onChange);
    };
  }

  return function useDeviceFlag() {
    const enabled = useSyncExternalStore(subscribe, read, () => true);
    const setEnabled = useCallback((next: boolean) => write(next), []);
    return [enabled, setEnabled];
  };
}
