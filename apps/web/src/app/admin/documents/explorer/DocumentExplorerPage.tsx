"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { Explorer } from "./Explorer";
import { Connector } from "@/lib/connectors/connectors";
import { DocumentSetSummary } from "@/lib/types";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

interface DocumentExplorerPageProps {
  initialSearchValue: string | undefined;
  connectors: Connector<any>[];
  documentSets: DocumentSetSummary[];
}

export default function DocumentExplorerPage({
  initialSearchValue,
  connectors,
  documentSets,
}: DocumentExplorerPageProps) {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_EXPLORER]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        separator
      />

      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.documentExplorer.workspaceTitle", {
            defaultValue: "Document explorer workspace",
          })}
          description={t("admin.documentExplorer.workspaceDescription", {
            defaultValue:
              "Search indexed content, narrow by connector or document set, and inspect what agents can retrieve.",
          })}
          metrics={[
            {
              label: t("admin.documentExplorer.connectorsLabel", {
                defaultValue: "Connectors",
              }),
              value: String(connectors.length),
            },
            {
              label: t("admin.documentExplorer.documentSetsLabel", {
                defaultValue: "Document sets",
              }),
              value: String(documentSets.length),
            },
            {
              label: t("admin.documentExplorer.searchModeLabel", {
                defaultValue: "Search mode",
              }),
              value: initialSearchValue
                ? t("admin.documentExplorer.prefilled", {
                    defaultValue: "Prefilled",
                  })
                : t("admin.documentExplorer.openSearch", {
                    defaultValue: "Open search",
                  }),
            },
          ]}
          actions={[
            {
              label: t("admin.navigation.routes.documentSets.sidebar", {
                defaultValue: "Document Sets",
              }),
              href: ADMIN_PATHS.DOCUMENT_SETS,
            },
            {
              label: t("admin.navigation.routes.documentFeedback.sidebar", {
                defaultValue: "Feedback",
              }),
              href: ADMIN_PATHS.DOCUMENT_FEEDBACK,
              primary: true,
            },
          ]}
        />
        <Explorer
          initialSearchValue={initialSearchValue}
          connectors={connectors}
          documentSets={documentSets}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
