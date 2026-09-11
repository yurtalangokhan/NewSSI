/**
 * Top bar of the flow studio (FlowAgentEditorPage) — the visual
 * equivalent of the classic agent editor's top bar + save button, grown
 * into the studio's full chrome: exit, settings, status/history, and
 * publish.
 *
 * Requirements addressed:
 * - 28.1: Shows current version status (Draft, Published, Draft ahead of vX)
 * - 28.2: Shows unsaved changes indicator (orange dot) when local graph is dirty
 * - 28.3: Publish button — disabled when clean, saving, or invalid
 * - 28.4: Inline error display for validation failures
 * - 28.5: Conflict detection (HTTP 409) with "Reload and retry" button
 * - 28.8: Permission gate (`flow:publish`)
 * - P7 Task 44: Test/Playground trigger button (permission gate `flow:execute`)
 * - Task 45: History trigger button opens VersionHistoryPanel
 * - Import Flow JSON with drag & drop and code editor modal
 * - P4→flow-separation: exit button (`onExit`) and a clickable agent
 *   name/avatar opening settings (`onOpenSettings`).
 *
 * Every action here appears exactly once. An earlier revision added a
 * publish split-button whose dropdown repeated Import JSON and Settings
 * (already an icon button and the agent-name button respectively) and
 * offered a manual "save draft" that autosave makes redundant; discarding
 * a draft belongs to the exit confirmation, which is where the user is
 * actually deciding the draft's fate. The dropdown is gone.
 *
 * Error handling:
 * - When `publish()` returns a 422 with a field-level error list, this bar
 *   renders the message and highlights the responsible node by matching
 *   its `node_id` (also written into the store by `useFlowValidation` so
 *   `TemplateNode` paints the actual node — see that hook's header).
 * - Client-side validation (`hasErrors`) blocks Publish as an
 *   affordance; the server validates regardless (P3's real gate).
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

"use client";

import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { useStore, type StoreApi } from "zustand";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import Text from "@/refresh-components/texts/Text";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { useUser } from "@/providers/UserProvider";
import {
  SvgArrowLeft,
  SvgGlobe,
  SvgHistory,
  SvgImport,
  SvgPlayCircle,
  SvgRefreshCw,
} from "@opal/icons";
import { saveDraftNow } from "../hooks/useFlowDraft";
import { useFlowValidation } from "../hooks/useFlowValidation";
import {
  useFlowVersions,
  type FlowVersion,
  type PublishIssue,
} from "../hooks/useFlowVersions";
import type { FlowStore } from "../stores/flowStore";
import { useFlowImport } from "../hooks/useFlowImport";
import { ImportFlowModal } from "./ImportFlowModal";
import { PublishFlowModal } from "./PublishFlowModal";
import { toast } from "@/hooks/useToast";

export type VersionBarProps = {
  definitionId: string;
  store: StoreApi<FlowStore>;
  onTogglePlayground?: () => void;
  isPlaygroundOpen?: boolean;
  /** Task 45 — opens/closes the VersionHistoryPanel mounted by the page. */
  onToggleHistory?: () => void;
  isHistoryOpen?: boolean;
  /** The flow's own persona snapshot — shown as avatar + name next to the
   * exit button. Absent when the bar is mounted outside the studio route
   * (e.g. inline in the classic editor), which just hides that group. */
  agent?: MinimalPersonaSnapshot;
  /** "Back to flows" — leaves the studio (guarded by useFlowExitGuard at
   * the call site, Task 13). */
  onExit?: () => void;
  /** Opens FlowSettingsModal in edit mode. */
  onOpenSettings?: () => void;
};

function statusLabel(
  publishedVersion: FlowVersion | null,
  draftVersion: FlowVersion | null,
  t: TFunction
): string {
  if (!publishedVersion) return t("flowCanvas.versionBar.draft", "Draft");
  if (draftVersion) {
    return t(
      "flowCanvas.versionBar.draftAhead",
      `Draft ahead of v${publishedVersion.version_no}`,
      { version: publishedVersion.version_no }
    );
  }
  return t(
    "flowCanvas.versionBar.published",
    `Published v${publishedVersion.version_no}`,
    { version: publishedVersion.version_no }
  );
}

export function VersionBar({
  definitionId,
  store,
  onTogglePlayground,
  isPlaygroundOpen,
  onToggleHistory,
  isHistoryOpen,
  agent,
  onExit,
  onOpenSettings,
}: VersionBarProps) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useUser();
  const canPublish = hasAnyPermission(["flow:publish"]); // 28.8, P3 Task 18
  const canExecute = hasAnyPermission(["flow:execute"]); // P7 Task 44
  const isDirty = useStore(store, (s) => s.isDirty);

  const { isLoading, publishedVersion, draftVersion, publish, refresh } =
    useFlowVersions(definitionId);
  const { hasErrors } = useFlowValidation(store);

  const [isPublishing, setIsPublishing] = useState(false);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const [publishIssues, setPublishIssues] = useState<PublishIssue[]>([]);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { importFromFile, loadGraph } = useFlowImport(store);

  const handleModalImport = useCallback(
    (
      graph: Parameters<typeof loadGraph>[0],
      nodeCount: number,
      edgeCount: number
    ) => {
      loadGraph(graph, nodeCount, edgeCount);
    },
    [loadGraph]
  );

  const handleFileImport = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) importFromFile(file);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    },
    [importFromFile]
  );

  const runPublish = async (notes?: string) => {
    setIsPublishing(true);
    setConflictMessage(null);
    setPublishIssues([]);
    try {
      try {
        await saveDraftNow(definitionId, store);
      } catch (err) {
        console.error("Failed to save draft before publish:", err);
        toast.error(
          t(
            "flowCanvas.versionBar.draftSaveBeforePublishFailed",
            "Failed to save draft before publishing; last saved version will be published"
          )
        );
      }
      const result = await publish(undefined, notes);
      // Every outcome closes the modal: a conflict or validation failure
      // needs the top bar's own inline messaging (reload-and-retry, the
      // per-node issue list) to be reachable, not hidden behind an open
      // dialog.
      setPublishModalOpen(false);
      if (result.kind === "conflict") {
        setConflictMessage(
          result.message ??
            t(
              "flowCanvas.versionBar.publishedConcurrently",
              "The flow was published concurrently."
            )
        );
      } else if (result.kind === "invalid") {
        setPublishIssues(result.errors);
      } else if (result.kind === "success") {
        try {
          await saveDraftNow(definitionId, store);
        } catch {
          // Non-fatal, preserves publish success
        }
        await refresh();
      }
    } finally {
      setIsPublishing(false);
    }
  };

  const status = statusLabel(publishedVersion, draftVersion, t);

  return (
    <div
      className="flex h-12 w-full items-center justify-between border-b border-canvas-border bg-canvas-panel px-4"
      data-testid="version-bar"
    >
      <div className="flex items-center gap-3">
        {onExit && (
          <IconButton
            icon={SvgArrowLeft}
            tooltip={t("flowStudio.exitToFlows", "Back to flows")}
            aria-label={t("flowStudio.exitToFlows", "Back to flows")}
            onClick={onExit}
            data-testid="flow-studio-exit"
          />
        )}
        {agent && (
          <button
            type="button"
            data-testid="flow-studio-open-settings"
            onClick={onOpenSettings}
            title={t("flowStudio.settings", "Settings")}
            className="flex items-center gap-2 rounded-08 px-1.5 py-1 hover:bg-background-tint-02"
          >
            <AgentAvatar agent={agent} size={24} />
            {/* text-05 is the primary text token (90% alpha); text-01 is
                20% and was unreadable on the canvas panel in dark mode. */}
            <Text text05 mainUiBody className="font-semibold">
              {agent.name}
            </Text>
          </button>
        )}
        <div
          className="flex items-center gap-2"
          data-testid="flow-studio-status-chip"
        >
          <Text text03 secondaryBody data-testid="version-status">
            {status}
          </Text>
          {isDirty && (
            <span
              className="flex h-2 w-2 rounded-full bg-theme-amber-05"
              data-testid="unsaved-indicator"
              title={t(
                "flowCanvas.versionBar.unsavedChanges",
                "Unsaved changes"
              )}
            />
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {conflictMessage && (
          <div
            className="flex items-center gap-2"
            data-testid="publish-conflict"
          >
            <Text text03 secondaryBody className="text-destructive">
              {conflictMessage}
            </Text>
            <Button
              secondary
              leftIcon={SvgRefreshCw}
              onClick={() => void refresh()}
              data-testid="reload-and-retry-button"
            >
              {t("flowCanvas.versionBar.reloadAndRetry", "Reload and retry")}
            </Button>
          </div>
        )}

        {publishIssues.length > 0 && (
          <div className="flex flex-col gap-0.5" data-testid="publish-issues">
            {publishIssues.map((issue, i) => (
              <Text key={i} text03 secondaryBody className="text-destructive">
                {issue.node_id
                  ? t(
                      "flowCanvas.versionBar.nodeIssue",
                      `Node ${issue.node_id}: ${issue.message}`,
                      { id: issue.node_id, message: issue.message }
                    )
                  : issue.message}
              </Text>
            ))}
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={handleFileImport}
          data-testid="versionbar-flow-file-input"
        />
        <IconButton
          icon={SvgImport}
          tooltip={t("flowCanvas.importJson", "JSON Yükle")}
          aria-label={t("flowCanvas.importJson", "JSON Yükle")}
          onClick={() => setImportModalOpen(true)}
          data-testid="import-flow-trigger"
        />

        {/* Task 45 — the history popover became a full panel (Langflow's
            FlowVersionSidebar); this toggle hands open/close to the page. */}
        {onToggleHistory && (
          <IconButton
            icon={SvgHistory}
            tooltip={t("flowCanvas.versionBar.history", "Version history")}
            aria-label={t("flowCanvas.versionBar.history", "Version history")}
            transient={isHistoryOpen}
            onClick={onToggleHistory}
            data-testid="toggle-version-history"
          />
        )}

        {canExecute && onTogglePlayground && (
          <Button
            tertiary
            leftIcon={SvgPlayCircle}
            onClick={onTogglePlayground}
            transient={isPlaygroundOpen}
            data-testid="playground-trigger-button"
          >
            {t("flowCanvas.versionBar.run", "Run")}
          </Button>
        )}

        {canPublish && (
          <Button
            main
            leftIcon={SvgGlobe}
            disabled={isPublishing || isLoading || hasErrors}
            onClick={() => setPublishModalOpen(true)}
            data-testid="publish-button"
          >
            {t("flowCanvas.versionBar.publish", "Publish")}
          </Button>
        )}
      </div>

      <ImportFlowModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onImport={handleModalImport}
      />

      {publishModalOpen && (
        <PublishFlowModal
          nextVersionNo={(publishedVersion?.version_no ?? 0) + 1}
          currentVersionNo={publishedVersion?.version_no ?? null}
          isPublishing={isPublishing}
          onConfirm={(notes) => void runPublish(notes)}
          onClose={() => setPublishModalOpen(false)}
        />
      )}
    </div>
  );
}

/** Same component, named for what it is once mounted in the studio route
 * — call sites there prefer this name; the inline (classic-editor) mount
 * point keeps using `VersionBar`. */
export const FlowStudioTopBar = VersionBar;
