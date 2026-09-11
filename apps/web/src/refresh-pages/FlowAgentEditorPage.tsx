/**
 * The canvas mode of the agent editor — mounted instead of the classic
 * Formik form (`AgentEditorPage.tsx`) when `existingAgent.graph_schema
 * === "flow"`. Ties together every P4 piece: the canvas shell (Task 24),
 * component sidebar (Task 25), node renderer (Task 26), inspector +
 * toolbar (Task 27), and version bar + draft persistence (Task 28).
 *
 * Layout follows Langflow's FlowPage (vendor/langflow/pages/FlowPage):
 * the canvas is the page — it fills all remaining space — and the palette
 * is a panel over it that collapses to a trigger button, rather than a
 * column that permanently narrows the canvas. Upstream's
 * `MemoizedSidebarTrigger` (PageComponent/MemoizedComponents.tsx:43-90)
 * is the same idea: when the sidebar is closed, a small bordered pill
 * sits at the canvas's top-left to bring it back.
 *
 * The application's own navigation sidebar stays where it is — this page
 * renders inside it, not over it.
 *
 * `next/dynamic({ ssr: false })` at the call site (`AgentEditorPage.tsx`)
 * — not here — since `@xyflow/react` and the zustand store it drives
 * have no meaningful server-rendered state (R3).
 */

"use client";

import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { SvgSidebar } from "@opal/icons";
import { ComponentSidebar } from "@/components/flow-canvas/components/ComponentSidebar";
import { FlowEditorShell } from "@/components/flow-canvas/components/FlowEditorShell";
import { createNodeInspector } from "@/components/flow-canvas/components/NodeInspector";
import { FlowExitModal } from "@/components/flow-canvas/components/FlowExitModal";
import { VersionBar } from "@/components/flow-canvas/components/VersionBar";
import { VersionHistoryPanel } from "@/components/flow-canvas/components/VersionHistoryPanel";
import { PlaygroundPanel } from "@/components/flow-canvas/components/PlaygroundPanel";
import { createConnectionLine } from "@/components/flow-canvas/edges/ConnectionLine";
import { FlowCanvas } from "@/components/flow-canvas/FlowCanvas";
import { useComponentTemplates } from "@/components/flow-canvas/hooks/useComponentTemplates";
import { useFlowDraft } from "@/components/flow-canvas/hooks/useFlowDraft";
import { useFlowExitGuard } from "@/components/flow-canvas/hooks/useFlowExitGuard";
import { useFlowVersions } from "@/components/flow-canvas/hooks/useFlowVersions";
import {
  useHandleTypeLookup,
  useDropHandler,
} from "@/components/flow-canvas/hooks/useCanvasWiring";
import { createNodeTypes } from "@/components/flow-canvas/nodes/registry";
import { createFlowStore } from "@/components/flow-canvas/stores/flowStore";
import { useAgents } from "@/hooks/useAgents";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import FlowSettingsModal from "@/sections/modals/FlowSettingsModal";

export type FlowAgentEditorPageProps = {
  agentDefinitionId: string;
  /** Called once the user has left the studio (exit confirmed, or nothing
   * to confirm) — Task 13 wires this to the top bar's back button via
   * useFlowExitGuard. Optional so the inline (non-route) usage inside
   * AgentEditorPage keeps working without it. */
  onExited?: () => void;
};

export default function FlowAgentEditorPage({
  agentDefinitionId,
  onExited,
}: FlowAgentEditorPageProps) {
  const { t } = useTranslation();
  const store = useMemo(() => createFlowStore(), []);
  const { data: grouped } = useComponentTemplates();
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [playgroundOpen, setPlaygroundOpen] = useState(false);
  // Task 45 — Langflow's FlowPage owns its FlowVersionSidebar the same way:
  // the page owns open/close so the VersionBar toggle stays stateless.
  const [historyOpen, setHistoryOpen] = useState(false);
  useFlowDraft(agentDefinitionId, store);

  // The catalog already carries every persona's agent_definition_id — no
  // extra endpoint needed to find the one this canvas is editing.
  const { agents, refresh: refreshAgents } = useAgents();
  const agent = useMemo(
    () => agents.find((a) => a.agent_definition_id === agentDefinitionId),
    [agents, agentDefinitionId]
  );
  const settingsModal = useCreateModal();

  const { publishedVersion, draftVersion } = useFlowVersions(agentDefinitionId);
  const {
    requestExit,
    isConfirmOpen,
    keepDraft,
    discardAndExit,
    cancel,
    isDiscarding,
  } = useFlowExitGuard({
    definitionId: agentDefinitionId,
    store,
    hasDraft: Boolean(draftVersion),
    onExited: onExited ?? (() => {}),
  });

  const lookupHandleTypes = useHandleTypeLookup(store, grouped);
  const onDropComponentType = useDropHandler(store, grouped);
  const nodeTypes = useMemo(() => createNodeTypes(store), [store]);
  const NodeInspector = useMemo(() => createNodeInspector(store), [store]);

  // The connection line needs the template registry to pick its colour,
  // but must not be re-created on every templates refetch (xyflow treats a
  // new component identity as a remount). A ref keeps the identity stable
  // while still reading fresh data.
  const groupedRef = useRef(grouped);
  groupedRef.current = grouped;
  const connectionLineComponent = useMemo(
    () => createConnectionLine(() => groupedRef.current),
    []
  );

  return (
    // `langflow-canvas` scopes Langflow's design tokens (see
    // components/flow-canvas/langflow-theme.css) to the whole editor, so
    // the sidebar, inspector and version bar share the canvas's palette
    // rather than only the graph surface doing so.
    <div
      className="langflow-canvas flex h-full min-h-0 w-full flex-col bg-canvas-panel"
      data-testid="flow-agent-editor-page"
    >
      {agent && (
        <settingsModal.Provider>
          <FlowSettingsModal
            mode="edit"
            agent={agent}
            onSaved={() => {
              settingsModal.toggle(false);
              refreshAgents();
            }}
          />
        </settingsModal.Provider>
      )}

      {isConfirmOpen && (
        <FlowExitModal
          publishedVersionNo={publishedVersion?.version_no ?? null}
          isDiscarding={isDiscarding}
          onKeep={keepDraft}
          onDiscard={discardAndExit}
          onCancel={cancel}
        />
      )}

      <VersionBar
        definitionId={agentDefinitionId}
        store={store}
        agent={agent}
        onExit={onExited ? requestExit : undefined}
        onOpenSettings={() => settingsModal.toggle(true)}
        onTogglePlayground={() => setPlaygroundOpen((o) => !o)}
        isPlaygroundOpen={playgroundOpen}
        onToggleHistory={() => setHistoryOpen((o) => !o)}
        isHistoryOpen={historyOpen}
      />

      <FlowEditorShell
        store={store}
        className="relative flex min-h-0 flex-1 overflow-hidden"
      >
        {/* The palette is an overlay, not a column — closing it gives the
            canvas the full width instead of leaving a gap. */}
        <div
          className={cn(
            "absolute inset-y-0 left-0 z-10 transition-transform duration-200",
            paletteOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="relative h-full">
            <ComponentSidebar onCollapse={() => setPaletteOpen(false)} />
          </div>
        </div>

        {/* upstream MemoizedComponents.tsx:76-88 — the reopen pill */}
        {!paletteOpen && (
          <button
            type="button"
            aria-label={t(
              "flowCanvas.sidebar.openPanel",
              "Open component panel"
            )}
            data-testid="open-component-panel"
            onClick={() => setPaletteOpen(true)}
            className="absolute left-2 top-2 z-10 flex items-center gap-1.5 rounded-md border border-secondary-hover bg-canvas-panel px-3 py-1.5 text-sm text-primary shadow hover:bg-accent"
          >
            <SvgSidebar className="h-4 w-4" />
            {t("flowCanvas.sidebar.title", "Components")}
          </button>
        )}

        <div
          className={cn(
            "h-full min-w-0 flex-1 transition-[padding] duration-200",
            paletteOpen && "pl-64"
          )}
        >
          <FlowCanvas
            store={store}
            lookupHandleTypes={lookupHandleTypes}
            nodeTypes={nodeTypes}
            onDropComponentType={onDropComponentType}
            connectionLineComponent={connectionLineComponent}
          />
        </div>

        <NodeInspector />
        {/* Overlays the palette region (z-20 > z-10) exactly like upstream's
            sidebar does — closing it gives the canvas back its full width. */}
        <VersionHistoryPanel
          definitionId={agentDefinitionId}
          store={store}
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
        />
        <PlaygroundPanel
          definitionId={agentDefinitionId}
          open={playgroundOpen}
          onClose={() => setPlaygroundOpen(false)}
          store={store}
        />
      </FlowEditorShell>
    </div>
  );
}
