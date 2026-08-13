"use client";

import BackButton from "@/refresh-components/buttons/BackButton";
import { ErrorCallout } from "@/components/ErrorCallout";
import { ThreeDotsLoader } from "@/components/Loading";
import { SourceIcon } from "@/components/SourceIcon";
import { CCPairStatus, PermissionSyncStatus } from "@/components/Status";
import { toast } from "@/hooks/useToast";
import CredentialSection from "@/components/credentials/CredentialSection";
import Text from "@/refresh-components/texts/Text";
import {
  updateConnectorCredentialPairName,
  updateConnectorCredentialPairProperty,
} from "@/lib/connector";
import { credentialTemplates } from "@/lib/connectors/credentials";
import { errorHandlingFetcher } from "@/lib/fetcher";
import Title from "@/components/ui/title";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, use } from "react";
import useSWR, { mutate } from "swr";
import {
  AdvancedConfigDisplay,
  buildConfigEntries,
  ConfigDisplay,
} from "./ConfigDisplay";
import DeletionErrorStatus from "./DeletionErrorStatus";
import { IndexAttemptsTable } from "./IndexAttemptsTable";
import InlineFileManagement from "./InlineFileManagement";
import { buildCCPairInfoUrl, triggerIndexing } from "./lib";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  CCPairFullInfo,
  ConnectorCredentialPairStatus,
  IndexAttemptError,
  statusIsNotCurrentlyActive,
} from "./types";
import { EditableStringFieldDisplay } from "@/components/EditableStringFieldDisplay";
import EditPropertyModal from "@/components/modals/EditPropertyModal";
import { AdvancedOptionsToggle } from "@/components/AdvancedOptionsToggle";
import { deleteCCPair } from "@/lib/documentDeletion";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import * as Yup from "yup";
import {
  AlertCircle,
  PlayIcon,
  PauseIcon,
  Trash2Icon,
  RefreshCwIcon,
} from "lucide-react";
import IndexAttemptErrorsModal from "./IndexAttemptErrorsModal";
import usePaginatedFetch from "@/hooks/usePaginatedFetch";
import { IndexAttemptSnapshot } from "@/lib/types";
import { Spinner } from "@/components/Spinner";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DropdownMenuItemWithTooltip } from "@/components/ui/dropdown-menu-with-tooltip";
import { timeAgo } from "@/lib/time";
import { useStatusChange } from "./useStatusChange";
import { useReIndexModal } from "./ReIndexModal";
import Button from "@/refresh-components/buttons/Button";
import { SvgSettings } from "@opal/icons";
import i18n from "@/i18n/config";
import { useTranslation } from "react-i18next";

const getRefreshFrequencySchema = () =>
  Yup.object().shape({
    propertyValue: Yup.number()
      .typeError(i18n.t("admin.connector.propertyValueMustBeNumber"))
      .integer(i18n.t("admin.connector.propertyValueMustBeInteger"))
      .min(1, i18n.t("admin.connector.propertyValueMin1"))
      .required(i18n.t("admin.connector.propertyValueRequired")),
  });

const getPruneFrequencySchema = () =>
  Yup.object().shape({
    propertyValue: Yup.number()
      .typeError(i18n.t("admin.connector.propertyValueMustBeNumber"))
      .min(0.083, i18n.t("admin.connector.propertyValueMin5m"))
      .required(i18n.t("admin.connector.propertyValueRequired")),
  });

const ITEMS_PER_PAGE = 8;
const PAGES_PER_BATCH = 8;

function Main({ ccPairId }: { ccPairId: number }) {
  const { t } = useTranslation();
  const router = useRouter();

  const {
    data: ccPair,
    isLoading: isLoadingCCPair,
    error: ccPairError,
  } = useSWR<CCPairFullInfo>(
    buildCCPairInfoUrl(ccPairId),
    errorHandlingFetcher,
    { refreshInterval: 5000 } // 5 seconds
  );

  const {
    currentPageData: indexAttempts,
    isLoading: isLoadingIndexAttempts,
    currentPage,
    totalPages,
    goToPage,
  } = usePaginatedFetch<IndexAttemptSnapshot>({
    itemsPerPage: ITEMS_PER_PAGE,
    pagesPerBatch: PAGES_PER_BATCH,
    endpoint: `${buildCCPairInfoUrl(ccPairId)}/index-attempts`,
  });

  const { currentPageData: indexAttemptErrorsPage } =
    usePaginatedFetch<IndexAttemptError>({
      itemsPerPage: 10,
      pagesPerBatch: 1,
      endpoint: `/api/manage/admin/cc-pair/${ccPairId}/errors`,
    });

  // Initialize hooks at top level to avoid conditional hook calls
  const { showReIndexModal, ReIndexModal } = useReIndexModal(
    ccPair?.connector?.id ?? null,
    ccPair?.credential?.id ?? null,
    ccPairId
  );

  const {
    handleStatusChange,
    isUpdating: isStatusUpdating,
    ConfirmModal,
  } = useStatusChange(ccPair || null);

  const indexAttemptErrors = indexAttemptErrorsPage
    ? {
        items: indexAttemptErrorsPage,
        total_items: indexAttemptErrorsPage.length,
      }
    : null;

  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [editingRefreshFrequency, setEditingRefreshFrequency] = useState(false);
  const [editingPruningFrequency, setEditingPruningFrequency] = useState(false);
  const [showIndexAttemptErrors, setShowIndexAttemptErrors] = useState(false);

  const [showIsResolvingKickoffLoader, setShowIsResolvingKickoffLoader] =
    useState(false);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [showDeleteConnectorConfirmModal, setShowDeleteConnectorConfirmModal] =
    useState(false);
  const isSchedulingConnectorDeletionRef = useRef(false);

  const refresh = useCallback(() => {
    mutate(buildCCPairInfoUrl(ccPairId));
  }, [ccPairId]);

  const shouldConfirmConnectorDeletion = true;

  const scheduleConnectorDeletion = useCallback(async () => {
    if (!ccPair) return;
    if (isSchedulingConnectorDeletionRef.current) return;
    isSchedulingConnectorDeletionRef.current = true;

    try {
      await deleteCCPair(ccPair.connector.id, ccPair.credential.id, () =>
        mutate(buildCCPairInfoUrl(ccPair.id))
      );
      refresh();
    } catch (error) {
      console.error("Error deleting connector:", error);
    } finally {
      setShowDeleteConnectorConfirmModal(false);
      isSchedulingConnectorDeletionRef.current = false;
    }
  }, [ccPair, refresh]);

  const latestIndexAttempt = indexAttempts?.[0];
  const isResolvingErrors =
    (latestIndexAttempt?.status === "in_progress" ||
      latestIndexAttempt?.status === "not_started") &&
    latestIndexAttempt?.from_beginning &&
    // if there are errors in the latest index attempt, we don't want to show the loader
    !indexAttemptErrors?.items?.some(
      (error) => error.index_attempt_id === latestIndexAttempt?.id
    );

  const finishConnectorDeletion = useCallback(() => {
    router.push("/admin/indexing/status?message=connector-deleted");
  }, [router]);

  const handleStatusUpdate = async (
    newStatus: ConnectorCredentialPairStatus
  ) => {
    setShowIsResolvingKickoffLoader(true); // Show fullscreen spinner
    await handleStatusChange(newStatus);
    setShowIsResolvingKickoffLoader(false); // Hide fullscreen spinner
  };

  const triggerReIndex = async (fromBeginning: boolean) => {
    if (!ccPair) return;

    setShowIsResolvingKickoffLoader(true);

    try {
      const result = await triggerIndexing(
        fromBeginning,
        ccPair.connector.id,
        ccPair.credential.id,
        ccPair.id
      );

      if (result.success) {
        toast.success(
          `${
            fromBeginning
              ? t("admin.connector.reindexingStarted")
              : t("admin.connector.indexingUpdateStarted")
          } ${t("admin.connector.startedSuccessfully")}`
        );
      } else {
        toast.error(result.message || t("admin.connector.failedToStartIndexing"));
      }
    } catch (error) {
      console.error("Failed to trigger indexing:", error);
      toast.error(t("admin.connector.unexpectedIndexingError"));
    } finally {
      setShowIsResolvingKickoffLoader(false);
    }
  };

  useEffect(() => {
    if (isLoadingCCPair) {
      return;
    }
    if (ccPair && !ccPairError) {
      setHasLoadedOnce(true);
    }

    if (
      (hasLoadedOnce && (ccPairError || !ccPair)) ||
      (ccPair?.status === ConnectorCredentialPairStatus.DELETING &&
        !ccPair.connector)
    ) {
      finishConnectorDeletion();
    }
  }, [
    isLoadingCCPair,
    ccPair,
    ccPairError,
    hasLoadedOnce,
    finishConnectorDeletion,
  ]);

  const handleUpdateName = async (newName: string) => {
    try {
      const response = await updateConnectorCredentialPairName(
        ccPair?.id!,
        newName
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      mutate(buildCCPairInfoUrl(ccPairId));
      toast.success(t("admin.connector.connectorNameUpdated"));
    } catch (error) {
      toast.error(t("admin.connector.failedToUpdateName"));
    }
  };

  const handleRefreshEdit = async () => {
    setEditingRefreshFrequency(true);
  };

  const handlePruningEdit = async () => {
    setEditingPruningFrequency(true);
  };

  const handleRefreshSubmit = async (
    propertyName: string,
    propertyValue: string
  ) => {
    const parsedRefreshFreqMinutes = parseInt(propertyValue, 10);

    if (isNaN(parsedRefreshFreqMinutes)) {
      toast.error(t("admin.connector.invalidRefreshFrequency"));
      return;
    }

    // Convert minutes to seconds
    const parsedRefreshFreqSeconds = parsedRefreshFreqMinutes * 60;

    try {
      const response = await updateConnectorCredentialPairProperty(
        ccPairId,
        propertyName,
        String(parsedRefreshFreqSeconds)
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      mutate(buildCCPairInfoUrl(ccPairId));
      toast.success(t("admin.connector.refreshFrequencyUpdated"));
    } catch (error) {
      toast.error(t("admin.connector.failedToUpdateRefreshFrequency"));
    }
  };

  const handlePruningSubmit = async (
    propertyName: string,
    propertyValue: string
  ) => {
    const parsedFreqHours = parseFloat(propertyValue);

    if (isNaN(parsedFreqHours)) {
      toast.error(t("admin.connector.invalidPruningFrequency"));
      return;
    }

    // Convert hours to seconds
    const parsedFreqSeconds = parsedFreqHours * 3600;

    try {
      const response = await updateConnectorCredentialPairProperty(
        ccPairId,
        propertyName,
        String(parsedFreqSeconds)
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      mutate(buildCCPairInfoUrl(ccPairId));
      toast.success(t("admin.connector.pruningFrequencyUpdated"));
    } catch (error) {
      toast.error(t("admin.connector.failedToUpdatePruningFrequency"));
    }
  };

  if (isLoadingCCPair || isLoadingIndexAttempts) {
    return <ThreeDotsLoader />;
  }

  if (!ccPair || (!hasLoadedOnce && ccPairError)) {
    return (
      <ErrorCallout
        errorTitle={t("admin.connector.failedToFetchInfo", { id: ccPairId })}
        errorMsg={
          ccPairError?.info?.detail ||
          ccPairError?.toString() ||
          t("admin.connector.unknownError")
        }
      />
    );
  }

  const isDeleting = ccPair.status === ConnectorCredentialPairStatus.DELETING;

  const {
    prune_freq: pruneFreq,
    refresh_freq: refreshFreq,
    indexing_start: indexingStart,
  } = ccPair.connector;

  return (
    <>
      {showIsResolvingKickoffLoader && !isResolvingErrors && <Spinner />}
      {ReIndexModal}
      {ConfirmModal}

      {showDeleteConnectorConfirmModal && (
        <ConfirmEntityModal
          danger
          entityType="connector"
          entityName={ccPair.name}
          additionalDetails={t("admin.connector.deletionDetails")}
          onClose={() => {
            setShowDeleteConnectorConfirmModal(false);
          }}
          onSubmit={scheduleConnectorDeletion}
        />
      )}

      {editingRefreshFrequency && (
        <EditPropertyModal
          propertyTitle={t("admin.connector.refreshFrequencyTitle")}
          propertyDetails={t("admin.connector.refreshFrequencyDetails")}
          propertyName="refresh_frequency"
          propertyValue={String(Math.round((refreshFreq || 0) / 60))}
          validationSchema={getRefreshFrequencySchema()}
          onSubmit={handleRefreshSubmit}
          onClose={() => setEditingRefreshFrequency(false)}
        />
      )}

      {editingPruningFrequency && (
        <EditPropertyModal
          propertyTitle={t("admin.connector.pruningFrequencyTitle")}
          propertyDetails={t("admin.connector.pruningFrequencyDetails")}
          propertyName="pruning_frequency"
          propertyValue={String(
            ((pruneFreq || 0) / 3600).toFixed(3).replace(/\.?0+$/, "")
          )}
          validationSchema={getPruneFrequencySchema()}
          onSubmit={handlePruningSubmit}
          onClose={() => setEditingPruningFrequency(false)}
        />
      )}

      {showIndexAttemptErrors && indexAttemptErrors && (
        <IndexAttemptErrorsModal
          errors={indexAttemptErrors}
          onClose={() => setShowIndexAttemptErrors(false)}
          onResolveAll={async () => {
            setShowIndexAttemptErrors(false);
            setShowIsResolvingKickoffLoader(true);
            await triggerReIndex(true);
          }}
          isResolvingErrors={isResolvingErrors}
        />
      )}

      <BackButton />
      <div
        className="flex
        items-center
        justify-between
        h-16
        pb-2
        border-b
        border-neutral-200
        dark:border-neutral-600"
      >
        <div className="my-auto">
          <SourceIcon iconSize={32} sourceType={ccPair.connector.source} />
        </div>

        <div className="ml-2 overflow-hidden text-ellipsis whitespace-nowrap flex-1 mr-4">
          <EditableStringFieldDisplay
            value={ccPair.name}
            isEditable={ccPair.is_editable_for_current_user}
            onUpdate={handleUpdateName}
            scale={2.1}
          />
        </div>

        <div className="ml-auto flex gap-x-2">
          {ccPair.is_editable_for_current_user && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button leftIcon={SvgSettings} secondary>
                  {t("admin.connector.manage")}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItemWithTooltip
                  onClick={() => {
                    if (
                      !ccPair.indexing &&
                      ccPair.status !== ConnectorCredentialPairStatus.PAUSED &&
                      ccPair.status !== ConnectorCredentialPairStatus.INVALID
                    ) {
                      showReIndexModal();
                    }
                  }}
                  disabled={
                    ccPair.indexing ||
                    ccPair.status === ConnectorCredentialPairStatus.PAUSED ||
                    ccPair.status === ConnectorCredentialPairStatus.INVALID
                  }
                  className="flex items-center gap-x-2 cursor-pointer px-3 py-2"
                  tooltip={
                    ccPair.indexing
                      ? t("admin.connector.cannotReindexWhileActive")
                      : ccPair.status === ConnectorCredentialPairStatus.PAUSED
                        ? t("admin.connector.resumeBeforeReindex")
                        : ccPair.status ===
                            ConnectorCredentialPairStatus.INVALID
                          ? t("admin.connector.fixConfigBeforeReindex")
                          : undefined
                  }
                >
                  <RefreshCwIcon className="h-4 w-4" />
                  <span>{t("admin.connector.reIndex")}</span>
                </DropdownMenuItemWithTooltip>
                {!isDeleting && (
                  <DropdownMenuItemWithTooltip
                    onClick={() =>
                      handleStatusUpdate(
                        statusIsNotCurrentlyActive(ccPair.status)
                          ? ConnectorCredentialPairStatus.ACTIVE
                          : ConnectorCredentialPairStatus.PAUSED
                      )
                    }
                    disabled={isStatusUpdating}
                    className="flex items-center gap-x-2 cursor-pointer px-3 py-2"
                    tooltip={
                      isStatusUpdating
                        ? t("admin.connector.statusUpdateInProgress")
                        : undefined
                    }
                  >
                    {statusIsNotCurrentlyActive(ccPair.status) ? (
                      <PlayIcon className="h-4 w-4" />
                    ) : (
                      <PauseIcon className="h-4 w-4" />
                    )}
                    <span>
                      {statusIsNotCurrentlyActive(ccPair.status)
                        ? t("admin.connector.resume")
                        : t("admin.connector.pause")}
                    </span>
                  </DropdownMenuItemWithTooltip>
                )}
                {!isDeleting && (
                  <DropdownMenuItemWithTooltip
                    onClick={async () => {
                      if (shouldConfirmConnectorDeletion) {
                        setShowDeleteConnectorConfirmModal(true);
                        return;
                      }

                      await scheduleConnectorDeletion();
                    }}
                    disabled={!statusIsNotCurrentlyActive(ccPair.status)}
                    className="flex items-center gap-x-2 cursor-pointer px-3 py-2 text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                    tooltip={
                      !statusIsNotCurrentlyActive(ccPair.status)
                        ? t("admin.connector.pauseBeforeDeleting")
                        : undefined
                    }
                  >
                    <Trash2Icon className="h-4 w-4" />
                    <span>{t("admin.connector.delete")}</span>
                  </DropdownMenuItemWithTooltip>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {ccPair.deletion_failure_message &&
        ccPair.status === ConnectorCredentialPairStatus.DELETING && (
          <>
            <div className="mt-6" />
            <DeletionErrorStatus
              deletion_failure_message={ccPair.deletion_failure_message}
            />
          </>
        )}

      {ccPair.status === ConnectorCredentialPairStatus.INVALID && (
        <div className="mt-6">
          <Callout
            type="warning"
            title={t("admin.connector.invalidConnectorState")}
          >
            {t("admin.connector.invalidConnectorStateBody")}
          </Callout>
        </div>
      )}

      {indexAttemptErrors && indexAttemptErrors.total_items > 0 && (
        <Alert className="border-alert bg-yellow-50 dark:bg-yellow-800 my-2 mt-6">
          <AlertCircle className="h-4 w-4 text-yellow-700 dark:text-yellow-500" />
          <AlertTitle className="text-yellow-950 dark:text-yellow-200 font-semibold">
            {t("admin.connector.someDocumentsFailed")}
          </AlertTitle>
          <AlertDescription className="text-yellow-900 dark:text-yellow-300">
            {isResolvingErrors ? (
              <span>
                <span className="text-sm text-yellow-700 dark:text-yellow-400 da animate-pulse">
                  {t("admin.connector.resolvingFailures")}
                </span>
              </span>
            ) : (
              <>
                {t("admin.connector.issuesProcessingDocuments")}{" "}
                <b
                  className="text-link cursor-pointer dark:text-blue-300"
                  onClick={() => setShowIndexAttemptErrors(true)}
                >
                  {t("admin.connector.viewDetails")}
                </b>
              </>
            )}
          </AlertDescription>
        </Alert>
      )}

      <Title className="mb-2 mt-6" size="md">
        {t("admin.connector.indexingTitle")}
      </Title>

      <Card className="px-8 py-12">
        <div className="flex">
          <div className="w-[200px]">
            <div className="text-sm font-medium mb-1">{t("admin.connector.statusLabel")}</div>
            <CCPairStatus
              ccPairStatus={ccPair.status}
              inRepeatedErrorState={ccPair.in_repeated_error_state}
              lastIndexAttemptStatus={latestIndexAttempt?.status}
            />
          </div>

          <div className="w-[200px]">
            <div className="text-sm font-medium mb-1">{t("admin.connector.documentsIndexed")}</div>
            <div className="text-sm text-text-default flex items-center gap-x-1">
              {ccPair.num_docs_indexed.toLocaleString()}
              {ccPair.status ===
                ConnectorCredentialPairStatus.INITIAL_INDEXING &&
                ccPair.overall_indexing_speed !== null &&
                ccPair.num_docs_indexed > 0 && (
                  <div className="ml-0.5 text-xs font-medium">
                    {t("admin.connector.indexingSpeed", {
                      speed: ccPair.overall_indexing_speed.toFixed(1),
                    })}
                  </div>
                )}
            </div>
          </div>

          <div className="w-[200px]">
            <div className="text-sm font-medium mb-1">{t("admin.connector.lastIndexed")}</div>
            <div className="text-sm text-text-default">
              {timeAgo(
                indexAttempts?.find((attempt) => attempt.status === "success")
                  ?.time_started
              ) ?? "-"}
            </div>
          </div>

          {ccPair.access_type === "sync" && (
            <>
              <div className="w-[200px]">
                {/* TODO: Remove className and switch to text03 once Text is fully integrated across this page */}
                <Text as="p" className="text-sm font-medium mb-1">
                  {t("admin.connector.permissionSyncing")}
                </Text>
                {ccPair.permission_syncing ||
                ccPair.last_permission_sync_attempt_status ? (
                  <PermissionSyncStatus
                    status={ccPair.last_permission_sync_attempt_status}
                    errorMsg={ccPair.last_permission_sync_attempt_error_message}
                  />
                ) : (
                  <PermissionSyncStatus status={null} />
                )}
              </div>

              <div className="w-[200px]">
                {/* TODO: Remove className and switch to text03 once Text is fully integrated across this page */}
                <Text as="p" className="text-sm font-medium mb-1">
                  {t("admin.connector.lastSynced")}
                </Text>
                <Text as="p" className="text-sm text-text-default">
                  {ccPair.last_permission_sync_attempt_finished
                    ? timeAgo(ccPair.last_permission_sync_attempt_finished)
                    : timeAgo(ccPair.last_full_permission_sync) ?? "-"}
                </Text>
              </div>
            </>
          )}
        </div>
      </Card>

      {credentialTemplates[ccPair.connector.source] &&
        ccPair.is_editable_for_current_user && (
          <>
            <Title size="md" className="mt-10 mb-2">
              {t("admin.connector.credential")}
            </Title>

            <div className="mt-2">
              <CredentialSection
                ccPair={ccPair}
                sourceType={ccPair.connector.source}
                refresh={() => refresh()}
              />
            </div>
          </>
        )}

      {ccPair.connector.connector_specific_config &&
        Object.keys(ccPair.connector.connector_specific_config).length > 0 && (
          <>
            <Title size="md" className="mt-10 mb-2">
              {t("admin.connector.connectorConfiguration")}
            </Title>

            <Card className="px-8 py-4">
              <ConfigDisplay
                configEntries={buildConfigEntries(
                  ccPair.connector.connector_specific_config,
                  ccPair.connector.source
                )}
              />

              {/* Inline file management for file connectors */}
              {ccPair.connector.source === "file" &&
                ccPair.is_editable_for_current_user && (
                  <div className="mt-6">
                    <InlineFileManagement
                      connectorId={ccPair.connector.id}
                      onRefresh={refresh}
                    />
                  </div>
                )}
            </Card>
          </>
        )}

      <div className="mt-6">
        <div className="flex">
          <AdvancedOptionsToggle
            showAdvancedOptions={showAdvancedOptions}
            setShowAdvancedOptions={setShowAdvancedOptions}
            title={t("admin.connector.advanced")}
          />
        </div>
        {showAdvancedOptions && (
          <div className="pb-16">
            {(pruneFreq || indexingStart || refreshFreq) && (
              <>
                <Title size="md" className="mt-3 mb-2">
                  {t("admin.connector.advancedConfiguration")}
                </Title>
                <Card className="px-8 py-4">
                  <div>
                    <AdvancedConfigDisplay
                      pruneFreq={pruneFreq}
                      indexingStart={indexingStart}
                      refreshFreq={refreshFreq}
                      onRefreshEdit={handleRefreshEdit}
                      onPruningEdit={handlePruningEdit}
                    />
                  </div>
                </Card>
              </>
            )}

            <Title size="md" className="mt-6 mb-2">
              {t("admin.connector.indexingAttempts")}
            </Title>
            {indexAttempts && (
              <IndexAttemptsTable
                ccPair={ccPair}
                indexAttempts={indexAttempts}
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={goToPage}
              />
            )}
          </div>
        )}
      </div>
    </>
  );
}

export default function Page(props: { params: Promise<{ ccPairId: string }> }) {
  const params = use(props.params);
  const ccPairId = parseInt(params.ccPairId);

  return (
    <div className="mx-auto w-[800px]">
      <Main ccPairId={ccPairId} />
    </div>
  );
}
