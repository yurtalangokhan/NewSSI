/**
 * Formats duration milliseconds into human-readable run time string.
 *
 * Ported from apps/web/vendor/langflow/CustomNodes/GenericNode/components/NodeStatus/utils/format-run-time.ts
 * Spec: .tmp/flow-canvas-design.md section 9.1
 * Brief: .tmp/flow-canvas-task-45-brief.md
 *
 * Units are localized through the shared `duration.*` i18n keys — "ms" stays
 * as-is (universal), minutes/seconds read "dk"/"sn" in Turkish, "m"/"s" in
 * English. Uses the module-level i18n instance because this is a plain util
 * called outside the React tree.
 */

import i18n from "@/i18n/config";

export function formatRunTime(durationMs: number | null | undefined): string {
  if (durationMs === null || durationMs === undefined || durationMs < 0) {
    return i18n.t("duration.none", { defaultValue: "—" });
  }

  if (durationMs < 1000) {
    return i18n.t("duration.ms", {
      value: Math.round(durationMs),
      defaultValue: "{{value}}ms",
    });
  }

  if (durationMs < 60000) {
    return i18n.t("duration.seconds", {
      value: (durationMs / 1000).toFixed(2),
      defaultValue: "{{value}}s",
    });
  }

  const mins = Math.floor(durationMs / 60000);
  const secs = Math.floor((durationMs % 60000) / 1000);
  return i18n.t("duration.minutesSeconds", {
    minutes: mins,
    seconds: secs,
    defaultValue: "{{minutes}}m {{seconds}}s",
  });
}
