"use client";

import { useTranslation } from "react-i18next";

import CardSection from "@/components/admin/CardSection";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG } from "@/lib/navigation/admin-routes";
import McpProviderListSkeleton from "@/refresh-components/skeletons/McpProviderListSkeleton";
import Separator from "@/refresh-components/Separator";

export default function Loading() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MCP_CONFIG]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={t(route.descriptionKey || "", {
          defaultValue: route.description,
        })}
        separator
      />
      <SettingsLayouts.Body>
        <CardSection className="rounded-08">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-col gap-1.5">
              <div className="h-4 w-40 rounded bg-background-tint-02 animate-pulse" />
              <div className="h-3 w-24 rounded bg-background-tint-02 animate-pulse opacity-70" />
            </div>
            <div className="flex items-center gap-3">
              <div className="h-9 w-full rounded-08 bg-background-tint-02 animate-pulse sm:w-64" />
              <div className="h-9 w-28 rounded-08 bg-background-tint-02 animate-pulse" />
            </div>
          </div>
          <Separator noPadding />
          <McpProviderListSkeleton />
        </CardSection>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
