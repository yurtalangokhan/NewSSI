"use client";

import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/refresh-components/texts/Text";
import { SvgHardDrive } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import {
  useCollections,
  useGraphBuildStatus,
  useGraphCollections,
} from "@/lib/langconnect";
import { useAirbyteDatasources } from "@/lib/airbyte";
import CollectionsPanel from "./components/CollectionsPanel";
import DocumentsPanel from "./components/DocumentsPanel";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_PROCESSING]!;

// ---------------------------------------------------------------------------
// RAG management section
// ---------------------------------------------------------------------------

function RagManagementSection() {
  const { t } = useTranslation();
  const [selectedCollectionId, setSelectedCollectionId] = useState<
    string | null
  >(null);
  const [selectedIsDatasource, setSelectedIsDatasource] = useState(false);
  const { collections } = useCollections();
  const { datasources } = useAirbyteDatasources();
  const { graphCollections } = useGraphCollections();
  const { status: buildStatus } = useGraphBuildStatus(
    selectedCollectionId,
    Boolean(selectedCollectionId)
  );
  const isCollectionMutationLocked =
    buildStatus?.status === "pending" ||
    buildStatus?.status === "extracting" ||
    buildStatus?.status === "building";

  function handleCollectionSelect(id: string | null, isDatasource?: boolean) {
    setSelectedCollectionId(id);
    setSelectedIsDatasource(isDatasource ?? false);
  }

  const graphReadyCount = graphCollections.length;
  const selectedBuildProgress =
    selectedCollectionId && buildStatus
      ? `${Math.round(buildStatus.progress_percent ?? 0)}%`
      : t("admin.documentProcessing.noActiveBuild");

  return (
    <div className="flex flex-col gap-4">
      <AdminOverviewPanel
        icon={route.icon}
        title={t("admin.documentProcessing.pipelineTitle")}
        description={t("admin.documentProcessing.pipelineDescription")}
        metrics={[
          {
            label: t("admin.documentProcessing.collectionsMetricLabel"),
            value: String(collections.length),
            tone: collections.length > 0 ? "success" : "warning",
          },
          {
            label: t("admin.documentProcessing.dataSourcesMetricLabel"),
            value: String(datasources.length),
          },
          {
            label: t("admin.documentProcessing.graphReadyMetricLabel"),
            value: String(graphReadyCount),
            tone: graphReadyCount > 0 ? "success" : "neutral",
          },
          {
            label: t("admin.documentProcessing.buildProgressMetricLabel"),
            value: selectedBuildProgress,
            tone: isCollectionMutationLocked ? "warning" : "neutral",
          },
        ]}
        actions={[
          {
            label: t("admin.navigation.routes.knowledgeGraph.sidebar"),
            href: ADMIN_PATHS.KNOWLEDGE_GRAPH,
          },
          {
            label: t("admin.indexingStatus.addConnector"),
            href: ADMIN_PATHS.ADD_CONNECTOR,
            primary: true,
          },
        ]}
      />

      <CollectionsPanel
        selectedCollectionId={selectedCollectionId}
        onCollectionSelect={handleCollectionSelect}
        isCollectionMutationLocked={isCollectionMutationLocked}
      />

      {selectedCollectionId ? (
        <DocumentsPanel
          collectionId={selectedCollectionId}
          readOnly={selectedIsDatasource}
          isCollectionMutationLocked={isCollectionMutationLocked}
        />
      ) : (
        <CardSection>
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <SvgHardDrive
              className="h-8 w-8 stroke-text-03 opacity-40"
              aria-hidden
            />
            <Text as="p" mainContentMuted text03>
              {t("admin.documentProcessing.selectOrCreateCollection")}
            </Text>
          </div>
        </CardSection>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={t("admin.documentProcessing.langConnectRagDescription")}
        separator
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-8 pb-36">
          <RagManagementSection />
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
