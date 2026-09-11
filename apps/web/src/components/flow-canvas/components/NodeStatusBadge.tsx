/**
 * Badge showing node execution status, duration and token usage.
 *
 * Spec: .tmp/flow-canvas-design.md section 9.1
 * Brief: .tmp/flow-canvas-task-45-brief.md
 */

import { SvgCheck, SvgClock, SvgLoader, SvgX } from "@opal/icons";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import type { NodeRunStatus } from "../stores/flowStore";
import { formatRunTime } from "../utils/formatRunTime";

export type NodeStatusBadgeProps = {
  status: NodeRunStatus | null | undefined;
};

export function NodeStatusBadge({ status }: NodeStatusBadgeProps) {
  const { t } = useTranslation();
  if (!status) return null;

  const isRunning = status.status === "running";
  const isDone = status.status === "done";
  const isError = status.status === "error";

  const durationStr = formatRunTime(status.durationMs);

  return (
    <div
      className="flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium border bg-canvas-panel shadow-sm transition-colors duration-150"
      data-testid="node-status-badge"
      data-status={status.status}
    >
      {isRunning && (
        <>
          <SvgLoader
            className="h-3 w-3 animate-spin text-primary"
            data-testid="status-running-icon"
          />
          <Text text03 secondaryBody className="text-primary font-medium">
            {t("flowCanvas.nodeStatus.running", "Running…")}
          </Text>
        </>
      )}

      {isDone && (
        <>
          <SvgCheck
            className="h-3 w-3 text-theme-green-05"
            data-testid="status-done-icon"
          />
          <Text
            text03
            secondaryBody
            className="text-theme-green-05 font-medium"
          >
            {durationStr}
          </Text>
        </>
      )}

      {isError && (
        <>
          <SvgX
            className="h-3 w-3 text-destructive"
            data-testid="status-error-icon"
          />
          <Text text03 secondaryBody className="text-destructive font-medium">
            {t("flowCanvas.nodeStatus.failed", "Failed")}
          </Text>
        </>
      )}

      {status.status === "queued" && (
        <>
          <SvgClock
            className="h-3 w-3 text-muted-foreground"
            data-testid="status-queued-icon"
          />
          <Text text03 secondaryBody className="text-muted-foreground">
            {t("flowCanvas.nodeStatus.queued", "Queued")}
          </Text>
        </>
      )}

      {status.tokenCount !== null && status.tokenCount !== undefined && (
        <span className="text-[10px] text-muted-foreground ml-1">
          {t("flowCanvas.nodeStatus.tokens", "{{count}} tok", {
            count: status.tokenCount,
          })}
        </span>
      )}
    </div>
  );
}
