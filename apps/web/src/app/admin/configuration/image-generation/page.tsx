"use client";

import { notFound } from "next/navigation";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import ImageGenerationContent from "./ImageGenerationContent";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.IMAGE_GENERATION]!;

export default function Page() {
  notFound();

  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={t("admin.imageGeneration.description")}
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.imageGeneration.workspaceTitle", {
            defaultValue: "Image generation workspace",
          })}
          description={t("admin.imageGeneration.workspaceDescription", {
            defaultValue:
              "Connect image providers, review model availability, and keep visual generation ready for agent workflows.",
          })}
          metrics={[
            {
              label: t("admin.imageGeneration.providerLayerLabel", {
                defaultValue: "Provider layer",
              }),
              value: t("admin.imageGeneration.providersMetric", {
                defaultValue: "Providers",
              }),
            },
            {
              label: t("admin.imageGeneration.agentCapabilityLabel", {
                defaultValue: "Agent capability",
              }),
              value: t("admin.imageGeneration.images", {
                defaultValue: "Images",
              }),
            },
            {
              label: t("admin.imageGeneration.relatedConfigLabel", {
                defaultValue: "Related config",
              }),
              value: t("admin.navigation.routes.llmModels.sidebar", {
                defaultValue: "LLM Models",
              }),
            },
          ]}
        />
        <ImageGenerationContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
