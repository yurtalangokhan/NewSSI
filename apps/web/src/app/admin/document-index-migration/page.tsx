"use client";

import { useState } from "react";
import useSWR from "swr";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.INDEX_MIGRATION]!;

import Card from "@/refresh-components/cards/Card";
import { Content, ContentAction } from "@opal/layouts";
import Text from "@/refresh-components/texts/Text";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Button from "@/refresh-components/buttons/Button";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { useTranslation } from "react-i18next";

interface MigrationStatus {
  total_chunks_migrated: number;
  created_at: string | null;
  migration_completed_at: string | null;
  approx_chunk_count_in_vespa: number | null;
}

interface RetrievalStatus {
  enable_opensearch_retrieval: boolean;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function MigrationStatusSection() {
  const { t } = useTranslation();
  const { data, isLoading, error } = useSWR<MigrationStatus>(
    "/api/admin/opensearch-migration/status",
    errorHandlingFetcher
  );

  if (isLoading) {
    return (
      <Card>
        <Text headingH3>{t("admin.indexMigration.migrationStatus")}</Text>
        <Text mainUiBody text03>
          {t("admin.indexMigration.loading")}
        </Text>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Text headingH3>{t("admin.indexMigration.migrationStatus")}</Text>
        <Text mainUiBody text03>
          {t("admin.indexMigration.failedToLoadStatus")}
        </Text>
      </Card>
    );
  }

  const hasStarted = data?.created_at != null;
  const hasCompleted = data?.migration_completed_at != null;
  const isOngoing = hasStarted && !hasCompleted;

  const totalChunksMigrated = data?.total_chunks_migrated ?? 0;
  const approxTotalChunks = data?.approx_chunk_count_in_vespa;

  // Calculate percentage progress if migration is ongoing and we have approx
  // total chunks.
  const shouldShowProgress = isOngoing && approxTotalChunks;
  const progressPercentage = shouldShowProgress
    ? Math.min(99, (totalChunksMigrated / approxTotalChunks) * 100)
    : null;

  return (
    <Card>
      <Text headingH3>{t("admin.indexMigration.migrationStatus")}</Text>

      <ContentAction
        title={t("admin.indexMigration.started")}
        sizePreset="main-ui"
        variant="section"
        rightChildren={
          <Text mainUiBody>
            {hasStarted ? formatTimestamp(data.created_at!) : t("admin.indexMigration.notStarted")}
          </Text>
        }
      />

      <ContentAction
        title={t("admin.indexMigration.chunksMigrated")}
        sizePreset="main-ui"
        variant="section"
        rightChildren={
          <Text mainUiBody>
            {progressPercentage !== null
              ? t("admin.indexMigration.approxProgress", {
                  count: totalChunksMigrated,
                  percent: Math.round(progressPercentage),
                })
              : String(totalChunksMigrated)}
          </Text>
        }
      />

      <ContentAction
        title={t("admin.indexMigration.completed")}
        sizePreset="main-ui"
        variant="section"
        rightChildren={
          <Text mainUiBody>
            {hasCompleted
              ? formatTimestamp(data.migration_completed_at!)
              : hasStarted
                ? t("admin.indexMigration.inProgress")
                : t("admin.indexMigration.notStarted")}
          </Text>
        }
      />
    </Card>
  );
}

function RetrievalSourceSection() {
  const { t } = useTranslation();
  const { data, isLoading, error, mutate } = useSWR<RetrievalStatus>(
    "/api/admin/opensearch-migration/retrieval",
    errorHandlingFetcher
  );
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  const serverValue = data?.enable_opensearch_retrieval
    ? "opensearch"
    : "vespa";
  const currentValue = selectedSource ?? serverValue;
  const hasChanges = selectedSource !== null && selectedSource !== serverValue;

  async function handleUpdate() {
    setUpdating(true);
    try {
      const response = await fetch(
        "/api/admin/opensearch-migration/retrieval",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enable_opensearch_retrieval: currentValue === "opensearch",
          }),
        }
      );
      if (!response.ok) {
        throw new Error(t("admin.indexMigration.failedToUpdateRetrieval"));
      }
      await mutate();
      setSelectedSource(null);
    } finally {
      setUpdating(false);
    }
  }

  if (isLoading) {
    return (
      <Card>
        <Text headingH3>{t("admin.indexMigration.retrievalSource")}</Text>
        <Text mainUiBody text03>
          {t("admin.indexMigration.loading")}
        </Text>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Text headingH3>{t("admin.indexMigration.retrievalSource")}</Text>
        <Text mainUiBody text03>
          {t("admin.indexMigration.failedToLoadRetrieval")}
        </Text>
      </Card>
    );
  }

  return (
    <Card>
      <Content
        title={t("admin.indexMigration.retrievalSource")}
        description={t("admin.indexMigration.retrievalDescription")}
        sizePreset="main-ui"
        variant="section"
      />

      <InputSelect
        value={currentValue}
        onValueChange={setSelectedSource}
        disabled={updating}
      >
        <InputSelect.Trigger placeholder={t("admin.indexMigration.selectRetrievalSource")} />
        <InputSelect.Content>
          <InputSelect.Item value="vespa">Vespa</InputSelect.Item>
            {t("admin.indexMigration.vespaOption")}
        </InputSelect.Content>
      </InputSelect>

      {hasChanges && (
        <Button
          className="self-center"
          onClick={handleUpdate}
          disabled={updating}
        >
          {updating ? t("admin.indexMigration.updating") : t("admin.indexMigration.updateSettings")}
        </Button>
      )}
    </Card>
  );
}

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.titleKey ? t(route.titleKey, { defaultValue: route.title }) : route.title}
        description={t("admin.indexMigration.pageDescription")}
        separator
      />
      <SettingsLayouts.Body>
        <MigrationStatusSection />
        <RetrievalSourceSection />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
