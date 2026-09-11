/**
 * Ported from Langflow (MIT) — src/frontend/src/pages/FlowPage/components/
 * flowSidebarComponent/components/FlowVersionSidebar
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Adapted for Onyx:
 * - Our version model is draft/published/archived (P3), not Langflow's flat
 *   checkpoint list: the pinned "Current" row is backed by the draft row,
 *   and the history rows are published/archived versions only.
 * - Selecting a version previews it read-only on the canvas (upstream's
 *   versionPreviewStore idea) until "{t("flowCanvas.versionHistory.backToDraft", "Back to draft")}" restores the working
 *   graph from an in-memory snapshot. `FlowStore.isPreviewMode` guarantees
 *   the preview can never trigger the autosave that would overwrite the
 *   user's draft with the historical spec.
 * - No delete action: our history is append-only by design (spec §5.3).
 *   The destructive-looking action is Restore = rollback (re-publishes the
 *   target as a NEW version), gated on `flow:publish`, with an inline
 *   confirm instead of upstream's DeleteConfirmDialog.
 * - No 10s polling (upstream `refetchInterval: 10000`) — this hook shares
 *   SWR's cache key with VersionBar's `useFlowVersions`, so focus/mutation
 *   revalidation keeps both in sync without a timer.
 * - Leaf primitives are refresh-components + @opal icons, per STANDARDS.md;
 *   upstream's ui/sidebar shims are not vendored for this panel.
 *
 * Brief: .tmp/flow-canvas-task-45-brief.md
 */

"use client";

import { useTranslation } from "react-i18next";
import type { StoreApi } from "zustand";
import { cn } from "@/lib/utils";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import LineItem from "@/refresh-components/buttons/LineItem";
import Popover from "@/refresh-components/Popover";
import Text from "@/refresh-components/texts/Text";
import {
  SvgArrowUpDown,
  SvgCheck,
  SvgChevronDown,
  SvgDownload,
  SvgEye,
  SvgHistory,
  SvgLoader,
  SvgMoreHorizontal,
  SvgRefreshCw,
  SvgX,
} from "@opal/icons";
import { type FlowVersionStatus } from "../hooks/useFlowVersions";
import type { FlowStore } from "../stores/flowStore";
import { FlowDiffList } from "./FlowDiffList";
import { FieldDiffOverlay } from "./FieldDiffOverlay";
import { useVersionHistoryPanel } from "./useVersionHistoryPanel";

export type VersionHistoryPanelProps = {
  definitionId: string;
  store: StoreApi<FlowStore>;
  open: boolean;
  onClose: () => void;
};

function formatTimestamp(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function StatusChip({ status }: { status: FlowVersionStatus }) {
  const { t } = useTranslation();
  const statusLabel: Record<FlowVersionStatus, string> = {
    published: t("flowCanvas.versionHistory.statusPublished", "Published"),
    draft: t("flowCanvas.versionHistory.statusDraft", "Draft"),
    archived: t("flowCanvas.versionHistory.statusArchived", "Archived"),
  };
  return (
    <span
      className={cn(
        "shrink-0 rounded border px-1 py-px text-xs leading-4",
        status === "published"
          ? "border-primary/30 bg-primary/10 text-primary"
          : "border-canvas-border bg-muted text-muted-foreground"
      )}
      data-testid={`version-chip-${status}`}
    >
      {statusLabel[status]}
    </span>
  );
}

export function VersionHistoryPanel({
  definitionId,
  store,
  open,
  onClose,
}: VersionHistoryPanelProps) {
  const { t } = useTranslation();
  const {
    isLoading,
    error,
    draftVersion,
    refresh,
    canPublish,
    history,
    previewVersionNo,
    loadingVersionNo,
    panelError,
    restoreTarget,
    isRestoring,
    restoreResult,
    menuOpenFor,
    activeDiff,
    expandedField,
    compareMode,
    compareSelection,
    setPanelError,
    setRestoreTarget,
    setRestoreResult,
    setMenuOpenFor,
    setExpandedField,
    handlePreview,
    handleBackToDraft,
    handleRestore,
    handleToggleDraftDiff,
    handleToggleCompareWithPrevious,
    handleCompareRowClick,
    handleToggleCompareMode,
    handleExport,
  } = useVersionHistoryPanel({ definitionId, store });

  return (
    <>
      {/* Upstream keeps a preview indicator in the header; our header is the
          VersionBar, which knows nothing about preview state — so the banner
          floats over the canvas itself and outlives the panel being closed. */}
      {previewVersionNo !== null && (
        <div
          className="absolute left-1/2 top-3 z-30 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-canvas-border bg-canvas-panel px-3 py-1.5 shadow-lg"
          data-testid="version-preview-banner"
        >
          <SvgEye className="h-4 w-4 shrink-0 text-primary" />
          <Text mainUiBody text03 className="whitespace-nowrap">
            {t(
              "flowCanvas.versionHistory.previewBanner",
              "Viewing v{{version}} — read-only preview",
              { version: previewVersionNo }
            )}
          </Text>
          <Button
            tertiary
            leftIcon={SvgRefreshCw}
            onClick={handleBackToDraft}
            data-testid="back-to-draft"
          >
            {t("flowCanvas.versionHistory.backToDraft", "Back to draft")}
          </Button>
        </div>
      )}

      {open && (
        <div
          className="absolute inset-y-0 left-0 z-20 flex w-72 flex-col border-r border-canvas-border bg-canvas-panel shadow-2xl"
          data-testid="version-history-panel"
        >
          <div className="flex items-center justify-between border-b border-canvas-border px-3 py-2.5">
            <div className="flex items-center gap-2">
              <SvgHistory className="h-4 w-4 text-muted-foreground" />
              <Text mainUiBody className="font-semibold">
                {t("flowCanvas.versionHistory.title", "Version History")}
              </Text>
              {history.length > 0 && (
                <Text text03 secondaryBody data-testid="version-history-count">
                  {history.length}
                </Text>
              )}
            </div>
            <div className="flex items-center gap-1">
              {history.length > 1 && (
                <IconButton
                  icon={SvgArrowUpDown}
                  internal={!compareMode}
                  tertiary={compareMode}
                  tooltip={t(
                    "flowCanvas.versionHistory.diff.compareTwoVersions",
                    "Compare two versions"
                  )}
                  aria-label={t(
                    "flowCanvas.versionHistory.diff.compareTwoVersions",
                    "Compare two versions"
                  )}
                  onClick={handleToggleCompareMode}
                  data-testid="version-compare-mode-toggle"
                />
              )}
              <IconButton
                icon={SvgX}
                tooltip={t(
                  "flowCanvas.versionHistory.close",
                  "Close version history"
                )}
                aria-label={t(
                  "flowCanvas.versionHistory.close",
                  "Close version history"
                )}
                onClick={onClose}
                data-testid="version-history-close"
              />
            </div>
          </div>

          {compareMode && (
            <div
              className="border-b border-canvas-border bg-primary/10 px-3 py-1.5"
              data-testid="version-compare-hint"
            >
              <Text text03 secondaryBody>
                {compareSelection.length === 0
                  ? t(
                      "flowCanvas.versionHistory.diff.compareHintFirst",
                      "Select a version to compare."
                    )
                  : t(
                      "flowCanvas.versionHistory.diff.compareHintSecond",
                      "Select a second version."
                    )}
              </Text>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
            {/* upstream's pinned "Current" row (CURRENT_DRAFT_ID) */}
            <button
              type="button"
              onClick={() =>
                previewVersionNo !== null
                  ? handleBackToDraft()
                  : void handleToggleDraftDiff()
              }
              data-testid="version-current-draft"
              className={cn(
                "flex w-full items-center justify-between gap-2 border-b border-canvas-border px-3 py-2.5 text-left hover:bg-muted",
                previewVersionNo === null &&
                  "border-l-2 border-l-primary bg-primary/10"
              )}
            >
              <div className="flex flex-col items-start gap-0.5">
                <Text mainUiBody className="font-medium">
                  {t("flowCanvas.versionHistory.currentDraft", "Current draft")}
                </Text>
                <Text text03 secondaryBody>
                  {draftVersion
                    ? t(
                        "flowCanvas.versionHistory.draftSummary",
                        "Working version · v{{version}} in draft",
                        { version: draftVersion.version_no }
                      )
                    : t(
                        "flowCanvas.versionHistory.noDraftYet",
                        "No draft yet — your next edit creates one"
                      )}
                </Text>
              </div>
              <SvgChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                  activeDiff?.key === "draft" && "rotate-180"
                )}
              />
            </button>

            {activeDiff?.key === "draft" && (
              <div
                className="flex flex-col gap-1.5 border-b border-canvas-border bg-muted/30 px-3 py-2.5"
                data-testid="version-diff-accordion-draft"
              >
                <Text text03 secondaryBody className="font-medium">
                  {activeDiff.title}
                </Text>
                {activeDiff.entries === null ? (
                  <Text text03 secondaryBody data-testid="version-diff-loading">
                    {t(
                      "flowCanvas.versionHistory.diff.loading",
                      "Loading changes…"
                    )}
                  </Text>
                ) : (
                  <FlowDiffList
                    entries={activeDiff.entries}
                    onExpandField={setExpandedField}
                  />
                )}
              </div>
            )}

            {isLoading && (
              <div
                className="flex flex-col gap-2 p-3"
                data-testid="version-history-loading"
              >
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="flex flex-col gap-1.5 rounded-md border border-canvas-border p-2.5 bg-muted/20"
                  >
                    <div className="flex items-center justify-between">
                      <div className="h-4 w-16 rounded bg-muted animate-pulse" />
                      <div className="h-3.5 w-20 rounded bg-muted animate-pulse opacity-70" />
                    </div>
                    <div className="h-3 w-36 rounded bg-muted animate-pulse opacity-60" />
                  </div>
                ))}
              </div>
            )}

            {error && !isLoading && (
              <div className="flex flex-col items-center gap-2 px-3 py-6 text-center">
                <Text text03 className="text-destructive">
                  {t(
                    "flowCanvas.versionHistory.loadFailed",
                    "Failed to load versions."
                  )}
                </Text>
                <Button
                  tertiary
                  leftIcon={SvgRefreshCw}
                  onClick={() => void refresh()}
                >
                  {t("flowCanvas.versionHistory.retry", "Retry")}
                </Button>
              </div>
            )}

            {!isLoading && !error && history.length === 0 && (
              <div
                className="px-3 py-6 text-center"
                data-testid="version-history-empty"
              >
                <Text text03 secondaryBody>
                  {t(
                    "flowCanvas.versionHistory.noPublishedVersions",
                    "No published versions yet."
                  )}
                </Text>
              </div>
            )}

            {history.map((v) => {
              const isActive = previewVersionNo === v.version_no;
              const isDiffOpen = activeDiff?.key === v.version_no;
              const isCompareSelected = compareSelection.includes(v.version_no);
              return (
                <div key={v.id}>
                  <div
                    data-testid={`version-row-${v.version_no}`}
                    className={cn(
                      "flex items-center justify-between gap-1 border-b border-canvas-border px-3 py-2",
                      isActive && "bg-primary/10",
                      isCompareSelected && "bg-primary/10"
                    )}
                  >
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <div className="flex items-center gap-1.5">
                        <Text
                          mainUiBody
                          className="font-medium"
                        >{`v${v.version_no}`}</Text>
                        <StatusChip status={v.status} />
                      </div>
                      <Text text03 secondaryBody className="truncate">
                        {formatTimestamp(v.published_at ?? v.created_at) || "—"}
                      </Text>
                    </div>
                    {compareMode ? (
                      <button
                        type="button"
                        onClick={() => handleCompareRowClick(v.version_no)}
                        aria-pressed={isCompareSelected}
                        aria-label={t(
                          "flowCanvas.versionHistory.diff.selectForCompare",
                          "Select v{{version}} to compare",
                          {
                            version: v.version_no,
                          }
                        )}
                        data-testid={`version-compare-select-${v.version_no}`}
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                          isCompareSelected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-canvas-border text-transparent hover:border-primary/60"
                        )}
                      >
                        <SvgCheck className="h-3 w-3" />
                      </button>
                    ) : loadingVersionNo === v.version_no ? (
                      <SvgLoader
                        className="mr-1 h-4 w-4 shrink-0 animate-spin text-muted-foreground"
                        data-testid={`version-loading-${v.version_no}`}
                      />
                    ) : (
                      <Popover
                        open={menuOpenFor === v.version_no}
                        onOpenChange={(isOpen) =>
                          setMenuOpenFor(isOpen ? v.version_no : null)
                        }
                      >
                        <Popover.Trigger asChild>
                          <IconButton
                            internal
                            icon={SvgMoreHorizontal}
                            tooltip={t(
                              "flowCanvas.versionHistory.versionActions",
                              "Version actions"
                            )}
                            aria-label={t(
                              "flowCanvas.versionHistory.versionActionsFor",
                              "Version actions for v{{version}}",
                              { version: v.version_no }
                            )}
                            data-testid={`version-actions-${v.version_no}`}
                          />
                        </Popover.Trigger>
                        <Popover.Content width="md" align="end">
                          <Popover.Menu>
                            <LineItem
                              icon={SvgEye}
                              onClick={() => {
                                setMenuOpenFor(null);
                                void handlePreview(v.version_no);
                              }}
                            >
                              {t(
                                "flowCanvas.versionHistory.previewOnCanvas",
                                "Preview on canvas"
                              )}
                            </LineItem>
                            <LineItem
                              icon={SvgArrowUpDown}
                              onClick={() => {
                                setMenuOpenFor(null);
                                void handleToggleCompareWithPrevious(v);
                              }}
                            >
                              {t(
                                "flowCanvas.versionHistory.compareWithPrevious",
                                "Compare with previous"
                              )}
                            </LineItem>
                            <LineItem
                              icon={SvgDownload}
                              onClick={() => {
                                setMenuOpenFor(null);
                                void handleExport(v);
                              }}
                            >
                              {t(
                                "flowCanvas.versionHistory.exportJson",
                                "Export JSON"
                              )}
                            </LineItem>
                            {canPublish && v.status !== "published" ? (
                              <LineItem
                                icon={SvgHistory}
                                onClick={() => {
                                  setMenuOpenFor(null);
                                  setPanelError(null);
                                  setRestoreResult(null);
                                  setRestoreTarget(v);
                                }}
                              >
                                {t(
                                  "flowCanvas.versionHistory.revertToVersion",
                                  "Restore this version"
                                )}
                              </LineItem>
                            ) : null}
                          </Popover.Menu>
                        </Popover.Content>
                      </Popover>
                    )}
                  </div>
                  {isDiffOpen && (
                    <div
                      className="flex flex-col gap-1.5 border-b border-canvas-border bg-muted/30 px-3 py-2.5"
                      data-testid={`version-diff-accordion-${v.version_no}`}
                    >
                      <Text text03 secondaryBody className="font-medium">
                        {activeDiff?.title}
                      </Text>
                      {activeDiff?.entries === null ? (
                        <Text
                          text03
                          secondaryBody
                          data-testid="version-diff-loading"
                        >
                          {t(
                            "flowCanvas.versionHistory.diff.loading",
                            "Loading changes…"
                          )}
                        </Text>
                      ) : (
                        <FlowDiffList
                          entries={activeDiff?.entries ?? []}
                          onExpandField={setExpandedField}
                        />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {(panelError ?? restoreResult) && (
            <div
              className="border-t border-canvas-border px-3 py-2"
              data-testid="version-history-message"
            >
              {panelError ? (
                <Text text03 className="text-destructive">
                  {panelError}
                </Text>
              ) : (
                restoreResult !== null && (
                  <Text text03 secondaryBody>
                    {restoreResult}
                  </Text>
                )
              )}
            </div>
          )}

          {restoreTarget !== null && (
            <div
              className="flex flex-col gap-1 border-t border-canvas-border px-3 py-2.5"
              data-testid="restore-confirm"
            >
              <Text mainUiBody className="font-medium">
                {t(
                  "flowCanvas.versionHistory.restoreConfirmTitle",
                  "Restore v{{version}}?",
                  { version: restoreTarget.version_no }
                )}
              </Text>
              <Text text03 secondaryBody>
                {t(
                  "flowCanvas.versionHistory.restoreConfirmBody",
                  "The flow will be re-published as a new version. Your current draft is kept."
                )}
              </Text>
              <div className="mt-1 flex items-center justify-end gap-2">
                <Button
                  tertiary
                  disabled={isRestoring}
                  onClick={() => setRestoreTarget(null)}
                >
                  {t("flowCanvas.versionHistory.cancel", "Cancel")}
                </Button>
                <Button
                  main
                  leftIcon={SvgRefreshCw}
                  disabled={isRestoring}
                  onClick={() => void handleRestore()}
                  data-testid="restore-confirm-button"
                >
                  {isRestoring
                    ? t("flowCanvas.versionHistory.restoring", "Restoring…")
                    : t("flowCanvas.versionHistory.restore", "Restore")}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {expandedField && (
        <FieldDiffOverlay
          field={expandedField}
          onClose={() => setExpandedField(null)}
        />
      )}
    </>
  );
}
