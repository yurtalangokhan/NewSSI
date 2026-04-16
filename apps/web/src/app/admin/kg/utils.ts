import { useCallback, useRef } from "react";
import { useUser } from "@/providers/UserProvider";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";
import { KGConfig, KGConfigRaw } from "./interfaces";

export type KgExposedStatus = { kgExposed: boolean; isLoading: boolean };

export function useIsKGExposed(): KgExposedStatus {
  const { isAdmin } = useUser();
  const { data: kgExposedRaw, isLoading } = useSWR<boolean>(
    isAdmin ? "/api/admin/kg/exposed" : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      revalidateIfStale: false,
      revalidateOnReconnect: false,
    }
  );
  return { kgExposed: kgExposedRaw ?? false, isLoading };
}

export function sanitizeKGConfig(raw: KGConfigRaw): KGConfig {
  const coverage_start = new Date(raw.coverage_start);

  return {
    ...raw,
    coverage_start,
  };
}

/**
 * Convert snake_case or SCREAMING_SNAKE_CASE to human-readable Title Case.
 * e.g. "source_name" → "Source Name", "PR_review" → "PR Review"
 */
export function snakeToHumanReadable(str: string): string {
  return str
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase())
    .replace("Pr", "PR");
}

/**
 * Returns a stable debounced version of the given callback.
 * The returned function delays invocation by `delay` ms; rapid calls reset the timer.
 */
export function useDebounce<T extends unknown[]>(
  fn: (...args: T) => void,
  delay: number
): (...args: T) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  return useCallback(
    (...args: T) => {
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => fn(...args), delay);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn, delay]
  );
}
