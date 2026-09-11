/**
 * Formatting helpers for the playground run stats footer (token count +
 * elapsed time), matching Langflow's playground presentation.
 *
 * `formatTokenCount` mirrors
 * apps/web/vendor/langflow/utils/format-token-count.ts — re-implemented here
 * because `vendor/` is excluded from the web tsconfig and cannot be imported.
 */

/** "500" · "1.5K" · "2.3M"; null when there is nothing meaningful to show. */
export function formatTokenCount(
  count: number | null | undefined
): string | null {
  if (count == null || count <= 0) return null;

  if (count >= 1_000_000) {
    const millions = count / 1_000_000;
    return `${millions % 1 === 0 ? millions.toFixed(0) : millions.toFixed(1)}M`;
  }
  if (count >= 1_000) {
    const thousands = count / 1_000;
    return `${
      thousands % 1 === 0 ? thousands.toFixed(0) : thousands.toFixed(1)
    }K`;
  }
  return count.toString();
}

/** "840ms" · "66.3s" — one-decimal seconds once past a second, like the
 * Langflow playground footer (distinct from `formatRunTime`, which switches
 * to "1m 6s" for the node status badge). */
export function formatDuration(
  durationMs: number | null | undefined
): string | null {
  if (durationMs == null || durationMs < 0) return null;
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}
