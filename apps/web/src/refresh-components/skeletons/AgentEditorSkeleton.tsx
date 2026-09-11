import React from "react";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Card from "@/refresh-components/cards/Card";
import { SvgOnyxOctagon } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface AgentEditorSkeletonProps {
  isEditing?: boolean;
}

export function AgentEditorSkeleton({
  isEditing = false,
}: AgentEditorSkeletonProps) {
  const { t } = useTranslation();

  return (
    <SettingsLayouts.Root width="xl">
      <SettingsLayouts.Header
        icon={SvgOnyxOctagon}
        title={
          isEditing
            ? t("agentEditor.editAgentTitle", { defaultValue: "Ajanı Düzenle" })
            : t("agentEditor.createAgentTitle", {
                defaultValue: "Yeni Ajan Oluştur",
              })
        }
        rightChildren={
          <div className="flex items-center gap-2">
            <div className="h-9 w-20 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-9 w-32 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
        }
        separator
      />
      <SettingsLayouts.Body>
        <div className="flex w-full flex-col gap-6 md:gap-8">
          <div className="grid w-full items-start gap-6 lg:grid-cols-[minmax(0,1fr)_auto]">
            {/* Left Column: Form Fields */}
            <div className="flex min-w-0 flex-col gap-5">
              {/* Name Field */}
              <div className="flex flex-col gap-1.5">
                <div className="h-4 w-28 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-00 animate-pulse" />
              </div>

              {/* Description Field */}
              <div className="flex flex-col gap-1.5">
                <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                <div className="h-20 w-full rounded-08 border border-border-01 bg-background-neutral-00 animate-pulse" />
              </div>

              {/* Base Agent Field */}
              <div className="flex flex-col gap-1.5">
                <div className="h-4 w-32 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                <div className="h-3.5 w-64 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
                <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-00 animate-pulse" />
              </div>

              {/* LLM / Model Selector Card */}
              <Card>
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-1">
                      <div className="h-4 w-32 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                      <div className="h-3 w-56 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
                    </div>
                  </div>
                  <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse" />
                </div>
              </Card>

              {/* Instructions / System Prompt */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                  <div className="h-3.5 w-24 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
                </div>
                <div className="h-32 w-full rounded-08 border border-border-01 bg-background-neutral-00 animate-pulse" />
              </div>

              {/* Starter Messages Card */}
              <Card>
                <div className="flex flex-col gap-3">
                  <div className="h-4 w-40 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                  <div className="flex flex-col gap-2">
                    <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse" />
                    <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse" />
                  </div>
                </div>
              </Card>

              {/* Tools & Integrations Card */}
              <Card>
                <div className="flex items-center justify-between py-1">
                  <div className="flex flex-col gap-1">
                    <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                    <div className="h-3 w-64 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
                  </div>
                  <div className="h-5 w-9 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                </div>
              </Card>
            </div>

            {/* Right Column: Avatar Picker */}
            <div className="flex min-w-0 flex-col gap-4 lg:w-fit">
              <div className="flex flex-col gap-2">
                <div className="h-4 w-28 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                <div className="h-[7.5rem] w-[7.5rem] rounded-full border border-border-01 bg-background-neutral-00 flex items-center justify-center animate-pulse">
                  <div className="h-16 w-16 rounded-full bg-background-tint-03 dark:bg-background-tint-04" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

export default AgentEditorSkeleton;
