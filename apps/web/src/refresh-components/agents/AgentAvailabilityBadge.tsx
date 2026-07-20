"use client";

import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { getAgentAvailabilityIssues } from "@/lib/agentAvailability";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

interface AgentAvailabilityBadgeProps {
  agent: MinimalPersonaSnapshot;
  showLabel?: boolean;
  className?: string;
}

function labelForStatus(
  status: NonNullable<MinimalPersonaSnapshot["availability"]>["status"] | undefined,
  t: ReturnType<typeof useTranslation>["t"]
) {
  if (status === "available") {
    return t("agentAvailability.available", "Available");
  }
  if (status === "degraded") {
    return t("agentAvailability.degraded", "Degraded");
  }
  if (status === "unavailable") {
    return t("agentAvailability.unavailable", "Unavailable");
  }
  return t("agentAvailability.checking", "Checking");
}

function detailLabel(agent: MinimalPersonaSnapshot, label: string) {
  const issues = getAgentAvailabilityIssues(agent.availability).map(
    (check) => check.message
  );

  if (issues.length === 0) {
    return label;
  }

  return `${label}: ${issues.slice(0, 3).join(" ")}`;
}

export default function AgentAvailabilityBadge({
  agent,
  showLabel = false,
  className,
}: AgentAvailabilityBadgeProps) {
  const { t } = useTranslation();
  const status = agent.availability?.status;
  const label = labelForStatus(status, t);
  const details = detailLabel(agent, label);
  const available = status === "available";
  const degraded = status === "degraded";
  const unknown = status === undefined;

  return (
    <span
      title={details}
      aria-label={`Agent status: ${details}`}
      className={cn(
        "inline-flex items-center gap-1.5 min-w-0",
        showLabel &&
          "rounded-08 border border-border-02 bg-background-neutral-00 px-1.5 py-0.5",
        className
      )}
    >
      <span
        className={cn(
          "size-2 rounded-full shrink-0",
          unknown
            ? "bg-background-neutral-05"
            : available
              ? "bg-status-success-04"
              : degraded
                ? "bg-status-warning-05"
                : "bg-status-error-04"
        )}
      />
      {showLabel && (
        <Text
          as="span"
          secondaryBody
          className={cn(
            "leading-none",
            available
              ? "text-status-success-05"
              : degraded
                ? "text-status-warning-05"
                : unknown
                  ? "text-text-03"
                  : "text-status-error-05"
          )}
        >
          {label}
        </Text>
      )}
    </span>
  );
}
