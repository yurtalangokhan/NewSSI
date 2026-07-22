"use client";

import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import type { IconFunctionComponent } from "@opal/types";

export interface AdminOverviewMetric {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "warning";
}

export interface AdminOverviewAction {
  label: string;
  href: string;
  primary?: boolean;
}

export interface AdminOverviewPanelProps {
  title: string;
  description: string;
  icon: IconFunctionComponent;
  metrics?: AdminOverviewMetric[];
  actions?: AdminOverviewAction[];
  className?: string;
}

function metricToneClass(tone: AdminOverviewMetric["tone"]) {
  if (tone === "success") {
    return "border-status-success-02 bg-status-success-00";
  }
  if (tone === "warning") {
    return "border-status-warning-03 bg-status-warning-01";
  }
  return "border-border-01 bg-background-neutral-00";
}

export default function AdminOverviewPanel({
  title,
  description,
  icon: Icon,
  metrics = [],
  actions = [],
  className,
}: AdminOverviewPanelProps) {
  return (
    <section
      className={cn(
        "rounded-08 border border-border-01 bg-background-neutral-00 p-4 shadow-01",
        className
      )}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-01">
            <Icon className="h-5 w-5 stroke-text-04" />
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <Text as="p" headingH3 text01>
              {title}
            </Text>
            <Text as="p" secondaryBody text03 className="max-w-3xl">
              {description}
            </Text>
          </div>
        </div>

        {actions.length > 0 && (
          <div className="flex shrink-0 flex-wrap gap-2">
            {actions.map((action) => (
              <Button
                key={action.href}
                href={action.href}
                primary={action.primary}
                secondary={!action.primary}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>

      {metrics.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <div
              key={`${metric.label}-${metric.value}`}
              className={cn(
                "rounded-08 border px-3 py-2",
                metricToneClass(metric.tone)
              )}
            >
              <Text as="p" figureSmallLabel text03>
                {metric.label}
              </Text>
              <Text as="p" headingH3 text01>
                {metric.value}
              </Text>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
