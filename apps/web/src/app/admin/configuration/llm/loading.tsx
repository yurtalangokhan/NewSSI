"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import LLMConfigurationSkeleton from "@/refresh-components/skeletons/LLMConfigurationSkeleton";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";

export default function Loading() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.LLM_MODELS]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.llm.workspaceTitle", {
            defaultValue: "Model provider workspace",
          })}
          description={t("admin.llm.workspaceDescription", {
            defaultValue:
              "Manage built-in, local, and cloud model providers, then choose the default model users start from.",
          })}
          metrics={[
            {
              label: t("admin.llm.builtInProvidersTitle"),
              value: "",
              isLoading: true,
            },
            {
              label: t("admin.llm.localProvidersTitle"),
              value: "",
              isLoading: true,
            },
            {
              label: t("admin.llm.cloudProvidersTitle"),
              value: "",
              isLoading: true,
            },
          ]}
          isLoading={true}
        />
        <LLMConfigurationSkeleton />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
