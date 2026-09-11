"use client";

import { useEffect, useState } from "react";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import type { IconFunctionComponent } from "@opal/types";
import AdminOverviewPanelSkeleton from "@/refresh-components/skeletons/AdminOverviewPanelSkeleton";

const CAROUSEL_INTERVAL_MS = 3000;

export interface AdminOverviewMetricValue {
  value: string;
  tone?: "neutral" | "success" | "warning";
}

export interface AdminOverviewMetric {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "warning";
  isLoading?: boolean;
  /**
   * When provided with more than one entry, the tile ignores `value`/`tone`
   * and auto-rotates through these instead, with small dot indicators
   * showing position. A single-entry (or absent) array falls back to the
   * plain `value`/`tone` behavior.
   */
  values?: AdminOverviewMetricValue[];
}

export interface AdminOverviewPanelProps {
  title: string;
  description: string;
  icon: IconFunctionComponent;
  metrics?: AdminOverviewMetric[];
  className?: string;
  isLoading?: boolean;
}

function metricToneClass(
  tone: AdminOverviewMetric["tone"],
  isMetricLoading?: boolean
) {
  if (isMetricLoading) {
    return "border-border-01 bg-background-neutral-01";
  }
  if (tone === "success") {
    return "border-status-success-02 bg-status-success-00";
  }
  if (tone === "warning") {
    return "border-status-warning-02 bg-status-warning-00";
  }
  return "border-border-01 bg-background-neutral-01";
}

function metricValueToneClass(tone: AdminOverviewMetric["tone"]) {
  if (tone === "success") {
    return "text-status-success-05";
  }
  if (tone === "warning") {
    return "text-status-warning-05";
  }
  return "text-text-05";
}

function MetricTile({ metric }: { metric: AdminOverviewMetric }) {
  const carouselValues =
    metric.values && metric.values.length > 1 ? metric.values : null;
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!carouselValues) return;
    setIndex(0);
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % carouselValues.length);
    }, CAROUSEL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [carouselValues]);

  const current = carouselValues ? carouselValues[index]! : metric;
  const isMetricLoading = carouselValues
    ? !!metric.isLoading
    : metric.isLoading || metric.value === "..." || metric.value === "";

  return (
    <div
      className={cn(
        "min-w-[160px] flex-1 rounded-08 border px-3 py-2.5",
        metricToneClass(current.tone, isMetricLoading)
      )}
    >
      <Text as="p" figureSmallLabel text04>
        {metric.label}
      </Text>
      {isMetricLoading ? (
        <div className="mt-2 h-6 w-16 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
      ) : (
        <Text
          key={carouselValues ? index : undefined}
          as="p"
          headingH3
          text05
          className={cn(
            "mt-0.5",
            metricValueToneClass(current.tone),
            carouselValues && "animate-fadeIn"
          )}
        >
          {current.value}
        </Text>
      )}
      {carouselValues && (
        <div className="mt-1.5 flex items-center gap-1">
          {carouselValues.map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-1 w-1 rounded-full",
                i === index ? "bg-text-04" : "bg-border-02"
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AdminOverviewPanel({
  title,
  description,
  icon: Icon,
  metrics = [],
  className,
  isLoading = false,
}: AdminOverviewPanelProps) {
  const isAnyMetricLoading =
    metrics.length > 0 &&
    metrics.some((m) =>
      m.values && m.values.length > 1
        ? !!m.isLoading
        : m.isLoading || m.value === "..." || m.value === ""
    );
  const showSkeleton = isLoading || isAnyMetricLoading;

  if (showSkeleton) {
    return (
      <AdminOverviewPanelSkeleton
        metricsCount={metrics.length > 0 ? metrics.length : 3}
        className={className}
      />
    );
  }

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
            <Text as="p" headingH3 text05>
              {title}
            </Text>
            <Text as="p" secondaryBody text04 className="max-w-3xl">
              {description}
            </Text>
          </div>
        </div>
      </div>

      {metrics.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {metrics.map((metric) => (
            <MetricTile
              key={`${metric.label}-${metric.value}`}
              metric={metric}
            />
          ))}
        </div>
      )}
    </section>
  );
}
