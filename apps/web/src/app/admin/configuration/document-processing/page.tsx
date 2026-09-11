"use client";

import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/refresh-components/texts/Text";
import { SvgHardDrive } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import TableSkeleton from "@/refresh-components/skeletons/TableSkeleton";
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
  const { collections, isLoading: isCollectionsLoading } = useCollections();
  const { datasources, isLoading: isDatasourcesLoading } =
    useAirbyteDatasources();
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
        isLoading={isCollectionsLoading || isDatasourcesLoading}
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
      />

      {isCollectionsLoading || isDatasourcesLoading ? (
        <>
          {/* Collections Selector Panel Skeleton */}
          <CardSection className="flex flex-col gap-4">
            <div className="flex items-center gap-2 border-b border-border-01 pb-3">
              <div className="h-4 w-4 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
              <div className="h-5 w-40 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            </div>
            <div className="h-4 w-3/4 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse" />
          </CardSection>

          {/* Documents Panel / Table Skeleton */}
          <CardSection className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-3 border-b border-border-01">
              <div className="flex flex-col gap-1.5">
                <div className="h-5 w-32 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                <div className="h-3.5 w-60 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
              </div>
              <div className="flex items-center gap-2">
                <div className="h-9 w-48 rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse" />
                <div className="h-9 w-28 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
              </div>
            </div>
            <TableSkeleton
              rowCount={4}
              columns={[
                { type: "icon-text", width: "w-44", headerWidth: "w-20" },
                { type: "badge", width: "w-20", headerWidth: "w-16" },
                { type: "text", width: "w-24", headerWidth: "w-20" },
                { type: "text", width: "w-32", headerWidth: "w-24" },
                { type: "actions", width: "w-16", headerWidth: "w-16" },
              ]}
            />
          </CardSection>
        </>
      ) : (
        <>
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
        </>
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
