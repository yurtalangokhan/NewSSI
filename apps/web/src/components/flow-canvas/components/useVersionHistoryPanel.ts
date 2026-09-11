/**
 * State + effects + action handlers for VersionHistoryPanel — extracted so
 * the panel component is a rendering concern only. All preview/restore/diff/
 * compare/export logic lives here.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { cloneDeep } from "lodash";
import type { StoreApi } from "zustand";
import { useUser } from "@/providers/UserProvider";
import { useFlowVersions, type FlowVersion } from "../hooks/useFlowVersions";
import type { FlowStore } from "../stores/flowStore";
import {
  diffFlowSpecs,
  fromFlowSpec,
  toFlowSpec,
  type FlowDiffEntry,
} from "../utils/compile";
import type {
  CanvasEdge,
  CanvasNode,
  Viewport,
  WireFlowSpec,
} from "../types/flow";
import type { ExpandableField } from "./FlowDiffList";

const EMPTY_SPEC: WireFlowSpec = {
  version: "1.0",
  nodes: [],
  edges: [],
  viewport: null,
};

type DraftSnapshot = {
  graph: { nodes: CanvasNode[]; edges: CanvasEdge[]; viewport: Viewport };
  /** Restoring the snapshot must also restore the dirty flag it was
   * captured with, or unsaved edits survive visually but never autosave. */
  wasDirty: boolean;
};

export function useVersionHistoryPanel({
  definitionId,
  store,
}: {
  definitionId: string;
  store: StoreApi<FlowStore>;
}) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useUser();
  const canPublish = hasAnyPermission(["flow:publish"]); // same guard as VersionBar's Publish
  const {
    versions,
    isLoading,
    error,
    draftVersion,
    publishedVersion,
    rollback,
    refresh,
    getVersionDetail,
  } = useFlowVersions(definitionId);

  const [previewVersionNo, setPreviewVersionNo] = useState<number | null>(null);
  const [loadingVersionNo, setLoadingVersionNo] = useState<number | null>(null);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<FlowVersion | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreResult, setRestoreResult] = useState<string | null>(null);
  // Controlled per-row action menus: choosing an entry must close its popover
  // (LineItem is not a Popover.Close), and only one row's menu can be open.
  const [menuOpenFor, setMenuOpenFor] = useState<number | null>(null);
  const draftSnapshotRef = useRef<DraftSnapshot | null>(null);
  // Which row's diff accordion is open, if any — "draft" for the pinned
  // row, a version_no for a history row. Only one open at a time, same
  // rule as `menuOpenFor`'s row-action popovers.
  const [activeDiff, setActiveDiff] = useState<{
    key: "draft" | number;
    title: string;
    entries: FlowDiffEntry[] | null;
  } | null>(null);
  // The single field currently shown full-size over the canvas — set by
  // clicking a "changed" bullet whose value was too long for the
  // accordion's own narrow width.
  const [expandedField, setExpandedField] = useState<ExpandableField | null>(
    null
  );
  // Two-click compare mode for arbitrary (not necessarily adjacent)
  // versions — "Compare with previous" on a row's own menu covers the
  // common case, this covers v2-vs-v7. Selection order doesn't matter;
  // the diff always runs old→new by version_no.
  const [compareMode, setCompareMode] = useState(false);
  const [compareSelection, setCompareSelection] = useState<number[]>([]);

  // The draft row is represented by the pinned "Current draft" entry —
  // listing it again as v{n} would show the same thing twice.
  const history = versions.filter((v) => v.status !== "draft");

  async function handlePreview(versionNo: number) {
    if (previewVersionNo === versionNo || loadingVersionNo !== null) return;
    setPanelError(null);
    setRestoreResult(null);
    setLoadingVersionNo(versionNo);
    if (draftSnapshotRef.current === null) {
      const { nodes, edges, viewport, isDirty } = store.getState();
      draftSnapshotRef.current = {
        graph: { nodes: cloneDeep(nodes), edges: cloneDeep(edges), viewport },
        wasDirty: isDirty,
      };
    }
    try {
      const detail = await getVersionDetail(versionNo);
      if (!detail) {
        setPanelError(
          t(
            "flowCanvas.versionHistory.versionUnavailable",
            "Version {{version}} is no longer available.",
            { version: versionNo }
          )
        );
        return;
      }
      store.getState().setPreviewMode(true);
      store.getState().loadGraph(fromFlowSpec(detail.flow_spec));
      setPreviewVersionNo(versionNo);
    } catch {
      setPanelError(
        t(
          "flowCanvas.versionHistory.loadVersionFailed",
          "Failed to load version {{version}}.",
          { version: versionNo }
        )
      );
    } finally {
      setLoadingVersionNo(null);
    }
  }

  function handleBackToDraft() {
    const snapshot = draftSnapshotRef.current;
    if (snapshot) {
      store.getState().loadGraph(snapshot.graph);
      if (snapshot.wasDirty) {
        // `loadGraph` clears the dirty flag by contract; unsaved edits that
        // existed before the preview must go back to being unsaved edits.
        store.setState({ isDirty: true });
      }
    }
    store.getState().setPreviewMode(false);
    draftSnapshotRef.current = null;
    setPreviewVersionNo(null);
  }

  async function handleRestore() {
    if (!restoreTarget || isRestoring) return;
    setIsRestoring(true);
    setPanelError(null);
    try {
      // A banner pointing at a version row whose meaning is about to change
      // is worse than no banner — return to the working draft first.
      if (previewVersionNo !== null) handleBackToDraft();
      const restored = await rollback(restoreTarget.version_no);
      await refresh();
      setRestoreResult(
        t(
          "flowCanvas.versionHistory.restoreSuccess",
          "Restored v{{from}} — now published as v{{to}}.",
          {
            from: restoreTarget.version_no,
            to: restored.version_no,
          }
        )
      );
    } catch {
      setPanelError(
        t(
          "flowCanvas.versionHistory.restoreFailed",
          "Failed to restore v{{version}}.",
          { version: restoreTarget.version_no }
        )
      );
    } finally {
      setRestoreTarget(null);
      setIsRestoring(false);
    }
  }

  async function handleToggleDraftDiff() {
    if (activeDiff?.key === "draft") {
      setActiveDiff(null);
      setExpandedField(null);
      return;
    }
    setExpandedField(null);
    setActiveDiff({
      key: "draft",
      title: publishedVersion
        ? t(
            "flowCanvas.versionHistory.diff.draftChangesTitle",
            "Changes since v{{version}}",
            {
              version: publishedVersion.version_no,
            }
          )
        : t(
            "flowCanvas.versionHistory.diff.draftChangesTitleNoPublish",
            "Changes in draft"
          ),
      entries: null,
    });
    try {
      const { nodes, edges, viewport } = store.getState();
      const newSpec = toFlowSpec(nodes, edges, viewport);
      const oldDetail = publishedVersion
        ? await getVersionDetail(publishedVersion.version_no)
        : null;
      setActiveDiff((current) =>
        current?.key === "draft"
          ? {
              ...current,
              entries: diffFlowSpecs(
                oldDetail?.flow_spec ?? EMPTY_SPEC,
                newSpec
              ),
            }
          : current
      );
    } catch {
      setActiveDiff((current) =>
        current?.key === "draft" ? { ...current, entries: [] } : current
      );
    }
  }

  /** Loads and shows the diff between two published/archived versions
   * (or `null` for "nothing before this one" — the very first version),
   * keyed on `newVersionNo` so the accordion opens under the newer row
   * regardless of which of the two was actually clicked. Shared by
   * "Compare with previous" and the two-click arbitrary-version picker. */
  async function loadVersionDiff(
    oldVersionNo: number | null,
    newVersionNo: number,
    title: string
  ) {
    setExpandedField(null);
    setActiveDiff({ key: newVersionNo, title, entries: null });
    try {
      const [oldDetail, newDetail] = await Promise.all([
        oldVersionNo !== null
          ? getVersionDetail(oldVersionNo)
          : Promise.resolve(null),
        getVersionDetail(newVersionNo),
      ]);
      setActiveDiff((current) =>
        current?.key === newVersionNo
          ? {
              ...current,
              entries: newDetail
                ? diffFlowSpecs(
                    oldDetail?.flow_spec ?? EMPTY_SPEC,
                    newDetail.flow_spec
                  )
                : [],
            }
          : current
      );
    } catch {
      setActiveDiff((current) =>
        current?.key === newVersionNo ? { ...current, entries: [] } : current
      );
    }
  }

  async function handleToggleCompareWithPrevious(version: FlowVersion) {
    if (activeDiff?.key === version.version_no) {
      setActiveDiff(null);
      setExpandedField(null);
      return;
    }
    const previous = versions
      .filter((v) => v.status !== "draft" && v.version_no < version.version_no)
      .sort((a, b) => b.version_no - a.version_no)[0];
    await loadVersionDiff(
      previous?.version_no ?? null,
      version.version_no,
      previous
        ? t(
            "flowCanvas.versionHistory.diff.versionCompareTitle",
            "v{{from}} → v{{to}}",
            {
              from: previous.version_no,
              to: version.version_no,
            }
          )
        : t(
            "flowCanvas.versionHistory.diff.firstVersionTitle",
            "v{{version}} (first version)",
            {
              version: version.version_no,
            }
          )
    );
  }

  function handleCompareRowClick(versionNo: number) {
    setCompareSelection((current) => {
      if (current.includes(versionNo))
        return current.filter((v) => v !== versionNo);
      if (current.length < 2) return [...current, versionNo];
      // A third click while two are already picked starts a fresh pair —
      // keep the most recent selection, swap in the new one.
      return [current[1]!, versionNo];
    });
  }

  function handleToggleCompareMode() {
    setCompareMode((current) => !current);
    setCompareSelection([]);
  }

  useEffect(() => {
    if (compareSelection.length !== 2) return;
    const [a, b] = compareSelection as [number, number];
    const [older, newer] = a < b ? [a, b] : [b, a];
    void loadVersionDiff(
      older,
      newer,
      t(
        "flowCanvas.versionHistory.diff.versionCompareTitle",
        "v{{from}} → v{{to}}",
        { from: older, to: newer }
      )
    );
  }, [compareSelection]);

  async function handleExport(version: FlowVersion) {
    setPanelError(null);
    try {
      const detail = await getVersionDetail(version.version_no);
      if (!detail) {
        setPanelError(
          t(
            "flowCanvas.versionHistory.versionUnavailable",
            "Version {{version}} is no longer available.",
            { version: version.version_no }
          )
        );
        return;
      }
      const blob = new Blob([JSON.stringify(detail.flow_spec, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `flow-v${version.version_no}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setPanelError(
        t(
          "flowCanvas.versionHistory.exportFailed",
          "Failed to export v{{version}}.",
          { version: version.version_no }
        )
      );
    }
  }

  return {
    versions,
    isLoading,
    error,
    draftVersion,
    publishedVersion,
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
  };
}
