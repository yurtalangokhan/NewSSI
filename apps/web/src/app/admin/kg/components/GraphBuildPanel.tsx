"use client";

import { useState, useEffect, useMemo } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import {
  useGraphBuildStatus,
  useGraphCollections,
  useDocuments,
  buildGraph,
  deleteGraph,
  fetchGraphBuildStatus,
  pauseGraphBuild,
  resumeGraphBuild,
  stopGraphBuild,
  type GraphBuildStatus,
  type GraphBuildStatusResponse,
} from "@/lib/langconnect";
import { toast } from "@/hooks/useToast";
import { SvgActivity, SvgTrash, SvgAlertTriangle } from "@opal/icons";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

function StatusBadge({ status }: { status: GraphBuildStatus }) {
  const { t } = useTranslation();
  const config: Record<GraphBuildStatus, { label: string; className: string }> =
    {
      pending: {
        label: t("admin.kg.status.pending"),
        className:
          "border-border-01 bg-background-neutral-01 text-text-03",
      },
      extracting: {
        label: t("admin.kg.status.extracting"),
        className:
          "border-status-warning-03 bg-status-warning-01 text-status-warning-06",
      },
      building: {
        label: t("admin.kg.status.building"),
        className:
          "border-status-info-03 bg-status-info-01 text-status-info-06",
      },
      completed: {
        label: t("admin.kg.status.completed"),
        className:
          "border-status-success-03 bg-status-success-01 text-status-success-06",
      },
      failed: {
        label: t("admin.kg.status.failed"),
        className:
          "border-status-error-03 bg-status-error-01 text-status-error-06",
      },
    };
  const { label, className } = config[status];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border",
        className
      )}
    >
      {label}
    </span>
  );
}

function StatCounter({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-08 border border-border-01 bg-background-neutral-01 px-4 py-3">
      <Text
        as="p"
        mainUiAction
        text04
        className="text-lg font-semibold tabular-nums"
      >
        {value.toLocaleString()}
      </Text>
      <Text as="p" mainContentMuted text03 className="text-xs text-center">
        {label}
      </Text>
    </div>
  );
}

interface GraphBuildPanelProps {
  collectionId: string | null;
  onBuildComplete?: () => void;
}

export default function GraphBuildPanel({
  collectionId,
  onBuildComplete,
}: GraphBuildPanelProps) {
  const { t } = useTranslation();
  const [pollActive, setPollActive] = useState(false);
  const [isPollingPaused, setIsPollingPaused] = useState(false);
  const [isPollingStopped, setIsPollingStopped] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [lastKnownSnapshot, setLastKnownSnapshot] =
    useState<{ collectionId: string; status: GraphBuildStatusResponse } | null>(null);

  const {
    graphCollections,
    mutate: mutateGraphCollections,
  } = useGraphCollections();

  const graphCollectionSet = useMemo(
    () => new Set(graphCollections),
    [graphCollections]
  );

  const selectedHasGraph = !!collectionId && graphCollectionSet.has(collectionId);

  const { documents, isLoading: docsLoading } = useDocuments(collectionId);
  const hasDocuments = documents.length > 0;

  const { status, mutate: mutateStatus } = useGraphBuildStatus(collectionId, pollActive);

  useEffect(() => {
    if (status && collectionId) {
      setLastKnownSnapshot({ collectionId, status });
    }
  }, [status, collectionId]);

  const effectiveStatus =
    status ??
    (lastKnownSnapshot?.collectionId === collectionId ? lastKnownSnapshot.status : null);

  const currentStatus = effectiveStatus?.status;

  const computedPercent =
    effectiveStatus && effectiveStatus.total_chunks > 0
      ? Math.round(
          (effectiveStatus.processed_chunks / effectiveStatus.total_chunks) *
            100
        )
      : (effectiveStatus?.progress_percent ?? 0);

  const inProgress =
    currentStatus === "pending" ||
    currentStatus === "extracting" ||
    currentStatus === "building";

  useEffect(() => {
    if (inProgress && !isPollingPaused && !isPollingStopped) {
      setPollActive(true);
    } else if (currentStatus === "completed" || currentStatus === "failed") {
      setPollActive(false);
      setIsSubmitting(false);
      setIsPollingPaused(false);
      setIsPollingStopped(false);
      if (currentStatus === "completed") {
        mutateGraphCollections();
        onBuildComplete?.();
      }
    }
  }, [
    currentStatus,
    inProgress,
    isPollingPaused,
    isPollingStopped,
    onBuildComplete,
    mutateGraphCollections,
  ]);

  // Auto-resume polling when collection is selected (e.g. after page refresh)
  useEffect(() => {
    if (!collectionId) {
      setPollActive(false);
      setIsSubmitting(false);
      setIsPollingPaused(false);
      setIsPollingStopped(false);
      setLastKnownSnapshot(null);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const data = await fetchGraphBuildStatus(collectionId);
        if (cancelled) return;
        if (
          data.status === "pending" ||
          data.status === "extracting" ||
          data.status === "building"
        ) {
          setLastKnownSnapshot({ collectionId, status: data });
          if (data.is_paused) {
            setIsPollingPaused(true);
            setIsPollingStopped(false);
            setPollActive(false);
          } else if (!isPollingPaused && !isPollingStopped) {
            setPollActive(true);
          }
        }
      } catch {
        // No active build — nothing to resume
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [collectionId, isPollingPaused, isPollingStopped]);

  const handleBuild = async () => {
    if (!collectionId) return;
    setIsSubmitting(true);
    setIsPollingPaused(false);
    setIsPollingStopped(false);
    // Clear stale snapshot and SWR cache so the previous build's status
    // (e.g. 'failed') never flashes in the UI after a new build starts.
    setLastKnownSnapshot(null);
    await mutateStatus(undefined, { revalidate: false });
    try {
      await buildGraph({ collection_id: collectionId });
      // API has returned: initialize_build_progress() already wrote 'pending'
      // to the backend store synchronously, so turning on polling now will
      // immediately get the correct status — no synthetic data needed.
      setPollActive(true);
      toast.success(t("admin.kg.graphBuildStarted"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("admin.kg.graphBuildStartFailed"));
      setIsSubmitting(false);
    }
  };

  const handlePausePolling = async () => {
    if (!collectionId) return;
    try {
      await pauseGraphBuild(collectionId);
      setPollActive(false);
      setIsPollingPaused(true);
      setIsPollingStopped(false);
      toast.info(t("admin.kg.pausedTrackingInfo"));
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("admin.kg.graphBuildPauseFailed")
      );
    }
  };

  const handleStopPolling = async () => {
    if (!collectionId) return;
    try {
      await stopGraphBuild(collectionId);
      // Keep polling active so the frontend automatically detects the
      // final "failed" status and cleans up all state via the useEffect.
      setIsPollingPaused(false);
      setIsPollingStopped(false);
      setPollActive(true);
      toast.info(t("admin.kg.graphBuildStopRequested"));
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("admin.kg.graphBuildStopFailed")
      );
    }
  };

  const handleResumePolling = async () => {
    if (!collectionId) return;
    try {
      await resumeGraphBuild(collectionId);
      setIsPollingPaused(false);
      setIsPollingStopped(false);
      setPollActive(true);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("admin.kg.graphBuildResumeFailed")
      );
    }
  };

  const handleDelete = async () => {
    if (!collectionId) return;
    if (
      !window.confirm(
        t("admin.kg.deleteConfirm")
      )
    )
      return;
    setIsDeleting(true);
    try {
      await deleteGraph(collectionId);
      toast.success(t("admin.kg.graphDeleted"));
      setPollActive(false);
      mutateGraphCollections();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("admin.kg.graphDeleteFailed"));
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <CardSection className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Text as="p" headingH3 text05>
          {t("admin.kg.buildGraph")}
        </Text>
        <Text as="p" mainContentBody text04 className="leading-relaxed">
          {t("admin.kg.buildGraphDescription")}{" "}{t("admin.kg.selectCollectionToBuild")}
        </Text>
      </div>

      {!collectionId ? (
        <Text as="p" mainContentMuted text03 className="text-sm">
          {t("admin.kg.selectCollectionToBuild")}
        </Text>
      ) : (
        <>
          {/* No documents warning */}
          {!inProgress && !docsLoading && !hasDocuments && (
            <div className="flex items-start gap-2 rounded-08 border border-status-error-03 bg-status-error-01 p-3">
              <SvgAlertTriangle className="h-4 w-4 shrink-0 stroke-status-error-06 mt-0.5" />
              <Text as="p" mainContentBody text04 className="text-xs text-status-error-06">
                {t("admin.kg.noDocumentsForBuild")}
              </Text>
            </div>
          )}

          {/* Warning for already-built collections */}
          {selectedHasGraph && !inProgress && (
            <div className="flex items-start gap-2 rounded-08 border border-status-warning-03 bg-status-warning-01 p-3">
              <SvgAlertTriangle className="h-4 w-4 shrink-0 stroke-status-warning-06 mt-0.5" />
              <div className="flex flex-col gap-0.5">
                <Text
                  as="p"
                  mainUiAction
                  text04
                  className="text-xs font-medium text-status-warning-07"
                >
                  {t("admin.kg.buildWarningTitle")}
                </Text>
                <Text
                  as="p"
                  mainContentMuted
                  text03
                  className="text-xs text-status-warning-06"
                >
                  {t("admin.kg.buildWarningDescription")}
                </Text>
              </div>
            </div>
          )}

          {effectiveStatus && (inProgress || currentStatus === "completed") && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <Text as="p" mainContentMuted text03 className="text-xs font-medium uppercase tracking-wide">
                  {t("admin.kg.progress")}
                </Text>
                <StatusBadge status={effectiveStatus.status} />
              </div>

              {inProgress && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <Text as="p" mainContentMuted text03 className="text-xs">
                      {t("admin.kg.completion")}
                    </Text>
                    <Text
                      as="p"
                      mainUiAction
                      text04
                      className="text-xs font-semibold tabular-nums"
                    >
                      {computedPercent.toFixed(0)}%
                    </Text>
                  </div>
                  <div className="w-full bg-background-neutral-01 rounded-full h-2 border border-border-01 overflow-hidden">
                    <div
                      className="bg-theme-primary-04 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${computedPercent}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-4 gap-3">
                <StatCounter label={t("admin.kg.chunks")} value={effectiveStatus.total_chunks} />
                <StatCounter label={t("admin.kg.processed")} value={effectiveStatus.processed_chunks} />
                <StatCounter label={t("admin.kg.entities")} value={effectiveStatus.extracted_entities} />
                <StatCounter label={t("admin.kg.relations")} value={effectiveStatus.extracted_relations} />
              </div>
            </div>
          )}

          {currentStatus === "failed" && status?.error && (
            <Text
              as="p"
              mainContentBody
              text04
              className="text-status-error-06 text-sm"
            >
              {t("admin.kg.error")}: {status.error}
            </Text>
          )}

          {inProgress && isPollingPaused && (
            <Text as="p" mainContentMuted text03 className="text-sm">
              {t("admin.kg.pausedTrackingInfo")}
            </Text>
          )}

          {inProgress && isPollingStopped && (
            <Text as="p" mainContentMuted text03 className="text-sm">
              {t("admin.kg.stoppedTrackingInfo")}
            </Text>
          )}

          <div className="flex items-center gap-2 pt-1">
            <Button
              leftIcon={SvgActivity}
              onClick={handleBuild}
              disabled={inProgress || isSubmitting || !hasDocuments}
            >
              {inProgress
                ? t("admin.kg.building")
                : selectedHasGraph
                  ? t("admin.kg.rebuildGraph")
                  : t("admin.kg.buildGraph")}
            </Button>

            {inProgress && !isPollingPaused && !isPollingStopped && (
              <>
                <Button secondary onClick={handlePausePolling}>
                  {t("admin.kg.pauseBuild")}
                </Button>
                <Button danger onClick={handleStopPolling}>
                  {t("admin.kg.stopBuild")}
                </Button>
              </>
            )}

            {inProgress && (isPollingPaused || isPollingStopped) && (
              <Button secondary onClick={handleResumePolling}>
                {t("admin.kg.resumeBuild")}
              </Button>
            )}

            <Button
              danger
              leftIcon={SvgTrash}
              onClick={handleDelete}
              disabled={isDeleting || inProgress || !selectedHasGraph}
            >
              {t("admin.kg.deleteGraph")}
            </Button>
          </div>
          {/* Document list */}
          {!docsLoading && hasDocuments && (
            <div className="flex flex-col gap-2">
              <Text as="p" mainContentMuted text03 className="text-xs font-medium uppercase tracking-wide">
                {t("admin.kg.collectionDocuments")} ({documents.length})
              </Text>
              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto rounded-08 border border-border-01 bg-background-neutral-01 p-2">
                {documents.map((doc) => (
                  <div key={doc.id} className="flex items-center gap-2 px-2 py-1 rounded-04 hover:bg-background-neutral-02 text-xs text-text-03 truncate">
                    <span className="truncate">{(doc.metadata?.filename as string) || (doc.metadata?.title as string) || doc.id}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </CardSection>
  );
}
