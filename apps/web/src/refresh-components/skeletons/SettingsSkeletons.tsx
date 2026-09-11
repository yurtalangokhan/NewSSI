import React from "react";
import Card from "@/refresh-components/cards/Card";
import { Section } from "@/layouts/general-layouts";
import Separator from "@/refresh-components/Separator";
import { cn } from "@/lib/utils";

export function HorizontalFieldSkeleton({
  titleWidth = "w-32",
  descWidth = "w-64",
  controlType = "input",
  className,
}: {
  titleWidth?: string;
  descWidth?: string;
  controlType?: "input" | "switch" | "button";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-row items-center justify-between w-full py-1",
        className
      )}
    >
      <div className="flex flex-col gap-1.5 flex-1 pr-4">
        <div
          className={cn(
            "h-4 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse",
            titleWidth
          )}
        />
        <div
          className={cn(
            "h-3 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70",
            descWidth
          )}
        />
      </div>
      {controlType === "input" && (
        <div className="h-10 w-60 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
      )}
      {controlType === "switch" && (
        <div className="h-6 w-11 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
      )}
      {controlType === "button" && (
        <div className="h-10 w-36 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
      )}
    </div>
  );
}

export function GeneralSettingsSkeleton() {
  return (
    <Section gap={2} width="full">
      {/* Profile Section */}
      <Section gap={0.75}>
        <div className="h-6 w-24 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
        <Card>
          <HorizontalFieldSkeleton titleWidth="w-28" descWidth="w-64" />
          <HorizontalFieldSkeleton titleWidth="w-20" descWidth="w-72" />
        </Card>
      </Section>

      {/* Appearance Section */}
      <Section gap={0.75}>
        <div className="h-6 w-32 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
        <Card>
          <HorizontalFieldSkeleton titleWidth="w-28" descWidth="w-60" />
          <div className="flex flex-col gap-2 w-full pt-1">
            <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
            <div className="flex flex-wrap gap-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="w-[90px] h-[68px] rounded-lg bg-background-tint-03 dark:bg-background-tint-04 animate-pulse"
                />
              ))}
            </div>
          </div>
        </Card>
      </Section>

      <Separator noPadding />

      {/* Danger Zone Section */}
      <Section gap={0.75}>
        <div className="h-6 w-32 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
        <Card>
          <HorizontalFieldSkeleton
            titleWidth="w-36"
            descWidth="w-80"
            controlType="button"
          />
        </Card>
      </Section>
    </Section>
  );
}

export function ChatPreferencesSkeleton() {
  return (
    <Section gap={2} width="full">
      {/* Chats Section */}
      <Section gap={0.75}>
        <div className="h-6 w-20 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
        <Card>
          <HorizontalFieldSkeleton titleWidth="w-32" descWidth="w-64" />
          <HorizontalFieldSkeleton
            titleWidth="w-28"
            descWidth="w-72"
            controlType="switch"
          />
          <HorizontalFieldSkeleton titleWidth="w-36" descWidth="w-56" />
        </Card>
      </Section>

      {/* Personal Preferences & Memories Section */}
      <Section gap={0.75}>
        <div className="flex flex-col gap-1.5 w-full">
          <div className="h-4 w-44 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          <div className="h-3 w-80 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70 mb-1" />
          <div className="h-24 w-full rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-3" />
        </div>

        <div className="h-6 w-24 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
        <Card>
          <HorizontalFieldSkeleton
            titleWidth="w-40"
            descWidth="w-80"
            controlType="switch"
          />
          <HorizontalFieldSkeleton
            titleWidth="w-36"
            descWidth="w-72"
            controlType="switch"
          />
        </Card>
      </Section>

      {/* Prompt Shortcuts Section */}
      <Section gap={0.75}>
        <div className="h-6 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-1" />
        <Card>
          <HorizontalFieldSkeleton
            titleWidth="w-32"
            descWidth="w-64"
            controlType="switch"
          />
        </Card>
      </Section>
    </Section>
  );
}

export function EmailSettingsSkeleton() {
  return (
    <Section gap={0.75} width="full">
      <div className="flex flex-col gap-1.5 mb-1">
        <div className="h-6 w-48 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
        <div className="h-3.5 w-96 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
      </div>

      <Card>
        <HorizontalFieldSkeleton titleWidth="w-28" descWidth="w-64" />
        <HorizontalFieldSkeleton titleWidth="w-36" descWidth="w-72" />
        <HorizontalFieldSkeleton titleWidth="w-32" descWidth="w-60" />
        <HorizontalFieldSkeleton titleWidth="w-28" descWidth="w-64" />
        <HorizontalFieldSkeleton titleWidth="w-28" descWidth="w-60" />

        <div className="flex flex-row items-center justify-between w-full pt-3 border-t border-border-01 mt-1">
          <div className="h-3.5 w-44 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          <div className="flex flex-row gap-2">
            <div className="h-10 w-28 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-10 w-28 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
        </div>
      </Card>
    </Section>
  );
}
