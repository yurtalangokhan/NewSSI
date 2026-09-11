/**
 * InlineFlowDesigner — a local-only canvas mount used while creating a new
 * agent (R3, Task 28 follow-up).
 *
 * Why this exists:
 * While creating a new agent (`AgentEditorPage.tsx`), there is no
 * `agent_definition_id` yet — that only exists after the persona is saved.
 * The real `FlowAgentEditorPage` requires that ID because its version bar,
 * draft polling and publishing endpoints all key off it.
 *
 * `InlineFlowDesigner` solves this by mounting the full canvas suite
 * (`FlowCanvas`, `ComponentSidebar`, `NodeInspector`, `PlaygroundPanel`)
 * against an in-memory `flowStore`. It has NO VersionBar, NO draft
 * polling, NO publish button — just the visual design surface and a notice
 * explaining that saving happens with the agent itself.
 *
 * When the agent is finally saved, `AgentEditorPage` compiles whatever is
 * in this store via `toFlowSpec()` and saves it as the agent's first
 * draft.
 */

"use client";

import { useMemo, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useStore, type StoreApi } from "zustand";
import { SvgWorkflow, SvgPlayCircle, SvgImport } from "@opal/icons";
import { FlowCanvas } from "@/components/flow-canvas/FlowCanvas";
import { ComponentSidebar } from "@/components/flow-canvas/components/ComponentSidebar";
import { FlowEditorShell } from "@/components/flow-canvas/components/FlowEditorShell";
import { createNodeInspector } from "@/components/flow-canvas/components/NodeInspector";
import { PlaygroundPanel } from "@/components/flow-canvas/components/PlaygroundPanel";
import { ImportFlowModal } from "@/components/flow-canvas/components/ImportFlowModal";
import { useComponentTemplates } from "@/components/flow-canvas/hooks/useComponentTemplates";
import {
  useHandleTypeLookup,
  useDropHandler,
} from "@/components/flow-canvas/hooks/useCanvasWiring";
import { createNodeTypes } from "@/components/flow-canvas/nodes/registry";
import {
  createFlowStore,
  type FlowStore,
} from "@/components/flow-canvas/stores/flowStore";
import {
  isFlowJsonFile,
  useFlowImport,
} from "@/components/flow-canvas/hooks/useFlowImport";
import { getChatNodePresence } from "@/components/flow-canvas/utils/chatNodePresence";
import Button from "@/refresh-components/buttons/Button";
import { useUser } from "@/providers/UserProvider";
import Text from "@/refresh-components/texts/Text";

export type InlineFlowDesignerProps = {
  /** Test-only injection point; production callers always get the default
   * fresh, internally-owned store. */
  store?: StoreApi<FlowStore>;
};

export default function InlineFlowDesigner({
  store: injectedStore,
}: InlineFlowDesignerProps = {}) {
  const { t } = useTranslation();
  const ownStore = useMemo(() => createFlowStore(), []);
  const store = injectedStore ?? ownStore;
  const { data: grouped } = useComponentTemplates();
  const { hasAnyPermission } = useUser();
  const canExecute = hasAnyPermission(["flow:execute"]);
  const [playgroundOpen, setPlaygroundOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // The playground needs a ChatInput/ChatOutput pair to have anything to
  // run — testing an arrangement of resource nodes alone always fails the
  // same structural check the backend runs (FLOW_NO_EXIT), so the button
  // stays disabled until that's at least possible.
  const hasChatIO = useStore(store, (s) => {
    const { hasChatInput, hasChatOutput } = getChatNodePresence(s.nodes);
    return hasChatInput || hasChatOutput;
  });

  const lookupHandleTypes = useHandleTypeLookup(store, grouped);
  const onDropComponentType = useDropHandler(store, grouped);
  const nodeTypes = useMemo(() => createNodeTypes(store), [store]);
  const NodeInspector = useMemo(() => createNodeInspector(store), [store]);

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
      // Reset input value so re-selecting the same file works
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    },
    [importFromFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      const file = e.dataTransfer.files?.[0];
      if (file && isFlowJsonFile(file)) {
        e.preventDefault();
        e.stopPropagation();
        importFromFile(file);
      }
    },
    [importFromFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes("Files")) {
      e.preventDefault();
    }
  }, []);

  return (
    <div
      className="langflow-canvas flex h-[36rem] w-full flex-col gap-2"
      data-testid="inline-flow-designer"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={handleFileImport}
        data-testid="inline-flow-file-input"
      />

      {/* Notice Banner */}
      <div className="relative flex w-full items-center justify-between overflow-hidden rounded-12 border border-border-01 bg-background-neutral-01 px-4 py-3 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-08 border border-action-link-02 bg-action-link-01 text-action-link-05">
            <SvgWorkflow className="h-4 w-4 stroke-current" />
          </div>

          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-text-05">
                {t(
                  "agentEditor.flowCanvasSaveNoticeTitle",
                  "Design your flow here"
                )}
              </span>
              <span className="inline-flex items-center rounded-full border border-border-01 bg-background-neutral-00 px-2 py-0.5 text-[10px] font-medium text-text-04 shadow-2xs">
                {t("agentEditor.flowCanvasNoticeBadge", "Draft")}
              </span>
            </div>
            <Text as="p" className="text-xs text-text-03 leading-normal">
              {t(
                "agentEditor.flowCanvasSaveNotice",
                "This flow won't be saved until you finish creating the agent."
              )}
            </Text>
          </div>
        </div>
      </div>

      {/* The notice above stays outside the shell on purpose — it explains
          the form this designer is embedded in, and has no place on a
          fullscreen canvas. */}
      <FlowEditorShell
        store={store}
        className="relative flex flex-1 overflow-hidden rounded-md border border-canvas-border"
      >
        <ComponentSidebar />
        <div className="relative flex-1">
          <FlowCanvas
            store={store}
            lookupHandleTypes={lookupHandleTypes}
            nodeTypes={nodeTypes}
            onDropComponentType={onDropComponentType}
          />
        </div>
        <NodeInspector />
        <div className="absolute right-2 top-2 z-10 flex items-center gap-2">
          <Button
            secondary
            size="md"
            leftIcon={SvgImport}
            onClick={() => setImportModalOpen(true)}
            title={t(
              "flowCanvas.importJsonTooltip",
              "Import flow from JSON file"
            )}
            data-testid="inline-import-flow-trigger"
          >
            {t("flowCanvas.importJson", "Import JSON")}
          </Button>
          {canExecute && (
            <Button
              tertiary
              leftIcon={SvgPlayCircle}
              onClick={() => setPlaygroundOpen((open) => !open)}
              transient={playgroundOpen}
              disabled={!hasChatIO}
              title={
                hasChatIO
                  ? undefined
                  : t(
                      "agentEditor.flowCanvasTestDisabledTooltip",
                      "Add a Chat Input or Chat Output node to test this flow"
                    )
              }
              data-testid="inline-playground-trigger"
            >
              {t("agentEditor.flowCanvasTestButton", "Test")}
            </Button>
          )}
        </div>
        <PlaygroundPanel
          definitionId={null}
          open={playgroundOpen}
          onClose={() => setPlaygroundOpen(false)}
          store={store}
        />
      </FlowEditorShell>

      <ImportFlowModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onImport={handleModalImport}
      />
    </div>
  );
}
