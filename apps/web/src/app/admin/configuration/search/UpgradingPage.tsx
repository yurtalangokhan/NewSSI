import { ThreeDotsLoader } from "@/components/Loading";
import Modal from "@/refresh-components/Modal";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { useTranslation } from "react-i18next";
import {
  ConnectorIndexingStatusLite,
  ConnectorIndexingStatusLiteResponse,
  FailedConnectorIndexingStatus,
  ValidStatuses,
} from "@/lib/types";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import Button from "@/refresh-components/buttons/Button";
import { useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { ReindexingProgressTable } from "../../../../components/embedding/ReindexingProgressTable";
import { ErrorCallout } from "@/components/ErrorCallout";
import {
  CloudEmbeddingModel,
  HostedEmbeddingModel,
} from "../../../../components/embedding/interfaces";
import { Connector } from "@/lib/connectors/connectors";
import { FailedReIndexAttempts } from "@/components/embedding/FailedReIndexAttempts";
import { useConnectorIndexingStatusWithPagination } from "@/lib/hooks";
import { SvgX } from "@opal/icons";
import { ConnectorCredentialPairStatus } from "@/app/admin/connector/[ccPairId]/types";

export default function UpgradingPage({
  futureEmbeddingModel,
}: {
  futureEmbeddingModel: CloudEmbeddingModel | HostedEmbeddingModel;
}) {
  const { t } = useTranslation();
  const [isCancelling, setIsCancelling] = useState<boolean>(false);

  const { data: connectors, isLoading: isLoadingConnectors } = useSWR<
    Connector<any>[]
  >("/api/manage/connector", errorHandlingFetcher, {
    refreshInterval: 5000, // 5 seconds
  });

  const {
    data: connectorIndexingStatuses,
    isLoading: isLoadingOngoingReIndexingStatus,
  } = useConnectorIndexingStatusWithPagination(
    { secondary_index: true, get_all_connectors: true },
    5000
  ) as {
    data: ConnectorIndexingStatusLiteResponse[];
    isLoading: boolean;
  };

  const { data: failedIndexingStatus } = useSWR<
    FailedConnectorIndexingStatus[]
  >(
    "/api/manage/admin/connector/failed-indexing-status?secondary_index=true",
    errorHandlingFetcher,
    { refreshInterval: 5000 } // 5 seconds
  );

  const onCancel = async () => {
    const response = await fetch("/api/search-settings/cancel-new-embedding", {
      method: "POST",
    });
    if (response.ok) {
      mutate("/api/search-settings/get-secondary-search-settings");
    } else {
      alert(`Failed to cancel embedding model update - ${await response.text()}`);
    }
    setIsCancelling(false);
  };
  const statusOrder: Record<ValidStatuses, number> = useMemo(
    () => ({
      invalid: 0,
      failed: 1,
      canceled: 2,
      completed_with_errors: 3,
      not_started: 4,
      in_progress: 5,
      success: 6,
    }),
    []
  );

  const ongoingReIndexingStatus = useMemo(() => {
    return connectorIndexingStatuses
      .flatMap(
        (status) => status.indexing_statuses as ConnectorIndexingStatusLite[]
      )
      .filter((status) => status.cc_pair_id !== undefined);
  }, [connectorIndexingStatuses]);

  const visibleReindexingStatus = useMemo(() => {
    const statuses = ongoingReIndexingStatus || [];

    if (futureEmbeddingModel.switchover_type === "active_only") {
      return statuses.filter(
        (status) =>
          status.cc_pair_status !== ConnectorCredentialPairStatus.PAUSED
      );
    }

    return statuses;
  }, [futureEmbeddingModel.switchover_type, ongoingReIndexingStatus]);

  const sortedReindexingProgress = useMemo(() => {
    return [...(visibleReindexingStatus || [])].sort((a, b) => {
      const statusComparison =
        statusOrder[a.last_status || "not_started"] -
        statusOrder[b.last_status || "not_started"];

      if (statusComparison !== 0) {
        return statusComparison;
      }

      return (a.cc_pair_id || 0) - (b.cc_pair_id || 0);
    });
  }, [visibleReindexingStatus, statusOrder]);

  const hasVisibleReindexingProgress = sortedReindexingProgress.length > 0;

  if (isLoadingConnectors || isLoadingOngoingReIndexingStatus) {
    return <ThreeDotsLoader />;
  }

  return (
    <>
      {isCancelling && (
        <Modal open onOpenChange={() => setIsCancelling(false)}>
          <Modal.Content width="sm" height="sm">
            <Modal.Header
              icon={SvgX}
              title={t("admin.searchUpgrading.cancelTitle")}
              onClose={() => setIsCancelling(false)}
            />
            <Modal.Body>
              <div>{t("admin.searchUpgrading.cancelBody")}</div>
            </Modal.Body>
            <Modal.Footer>
              <Button onClick={onCancel}>{t("admin.searchUpgrading.confirmButton")}</Button>
              <Button onClick={() => setIsCancelling(false)} secondary>
                {t("admin.searchUpgrading.cancelButton")}
              </Button>
            </Modal.Footer>
          </Modal.Content>
        </Modal>
      )}

      {futureEmbeddingModel && (
        <div>
          <Title className="mt-8">{t("admin.searchUpgrading.currentStatusTitle")}</Title>
          <div className="mt-4">
            <div className="italic text-lg mb-2">
              {t("admin.searchUpgrading.switchingTo", { modelName: futureEmbeddingModel.model_name })}
            </div>

            <Button
              danger
              className="mt-4"
              onClick={() => setIsCancelling(true)}
            >
              {t("admin.searchUpgrading.cancelButton")}
            </Button>

            {connectors && connectors.length > 0 ? (
              futureEmbeddingModel.switchover_type === "instant" ? (
                <div className="mt-8">
                  <h3 className="text-lg font-semibold mb-2">
                    {t("admin.searchUpgrading.switchingModelsTitle")}
                  </h3>
                  <p className="mb-4 text-text-800">
                    {t("admin.searchUpgrading.instantSwitchBody")}
                  </p>
                  <p className="text-text-600">
                    {t("admin.searchUpgrading.newModelActiveSoon")}
                  </p>
                </div>
              ) : (
                <>
                  {failedIndexingStatus && failedIndexingStatus.length > 0 && (
                    <FailedReIndexAttempts
                      failedIndexingStatuses={failedIndexingStatus}
                    />
                  )}

                  <Text className="my-4">
                    {futureEmbeddingModel.switchover_type === "active_only" ? (
                      <>
                        {t("admin.searchUpgrading.activeOnlyProgress")}
                        <br />
                        {t("admin.searchUpgrading.activeOnlyProgressNote")}
                      </>
                    ) : (
                      <>
                        {t("admin.searchUpgrading.allConnectorsProgress")}
                        <br />
                        {t("admin.searchUpgrading.allConnectorsProgressNote")}
                      </>
                    )}
                  </Text>

                  {sortedReindexingProgress ? (
                    <>
                      {futureEmbeddingModel.switchover_type === "active_only" &&
                        !hasVisibleReindexingProgress && (
                          <Text className="text-text-700 mt-4">
                            {t("admin.searchUpgrading.allPausedText")}
                          </Text>
                        )}
                      {hasVisibleReindexingProgress && (
                        <ReindexingProgressTable
                          reindexingProgress={sortedReindexingProgress}
                        />
                      )}
                    </>
                  ) : (
                    <ErrorCallout errorTitle={t("admin.searchUpgrading.failedToFetchProgress")} />
                  )}
                </>
              )
            ) : (
              <div className="mt-8 p-6 bg-background-100 border border-border-strong rounded-lg max-w-2xl">
                <h3 className="text-lg font-semibold mb-2">
                  {t("admin.searchUpgrading.switchingModelsTitle")}
                </h3>
                <p className="mb-4 text-text-800">
                  {t("admin.searchUpgrading.noConnectorsBody")}
                </p>
                <p className="text-text-600">
                  {t("admin.searchUpgrading.newModelActiveSoon")}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
