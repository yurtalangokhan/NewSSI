"use client";

import { useCallback, useMemo } from "react";
import { createIdempotencyKey } from "@/lib/api/idempotency";

const STORAGE_PREFIX = "idem-key:";

function storageKey(operationId: string): string {
  return `${STORAGE_PREFIX}${operationId}`;
}

/**
 * Returns a stable idempotency key for a logical operation that must survive
 * page refresh or remount.
 *
 * The backend can only deduplicate retries when the same `Idempotency-Key` is
 * reused for the same logical operation. If a component generates a new key on
 * every render, effect run, or remount, the Redis layer never sees the same key
 * twice and deduplication is bypassed.
 *
 * This hook stores the key in `sessionStorage` keyed by an operation boundary,
 * so a page refresh within the same browser session recovers the same key.
 *
 * @example
 * ```tsx
 * const { key, clearKey } = useIdempotencyKey("create-assistant");
 *
 * const onSubmit = async () => {
 *   await authenticatedFetch("/api/assistants", {
 *     method: "POST",
 *     headers: withIdempotencyKey({}, key),
 *     body: JSON.stringify(payload),
 *   });
 *   clearKey(); // operation reached a terminal state
 * };
 * ```
 */
export function useIdempotencyKey(operationId: string): {
  key: string;
  clearKey: () => void;
} {
  const key = useMemo(() => {
    if (typeof window === "undefined") {
      return createIdempotencyKey();
    }
    const existing = window.sessionStorage.getItem(storageKey(operationId));
    if (existing) {
      return existing;
    }
    const fresh = createIdempotencyKey();
    window.sessionStorage.setItem(storageKey(operationId), fresh);
    return fresh;
  }, [operationId]);

  const clearKey = useCallback(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(storageKey(operationId));
    }
  }, [operationId]);

  return { key, clearKey };
}
