/**
 * Ported from Langflow (MIT) — src/frontend/src/pages/FlowPage/components/nodeToolbarComponent
 * (InspectionPanel concept) — Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * The side panel for the selected node. Task 26's `TemplateNode` renders
 * a node on the canvas (name, icon, handles, inline fields); this renders
 * everything else for the selected node, reusing the exact same
 * `NodeFieldList` (and, through it, `fields/`'s `FIELD_RENDERERS`) rather
 * than a second set (27.4).
 *
 * Needs no `ReactFlowProvider` — unlike `TemplateNode`, this reads only
 * the zustand store (selection, nodes) and never touches `@xyflow/react`
 * directly, so it can be tested and used standalone next to `FlowCanvas`.
 *
 * `createNodeInspector(store)` is a factory for the same reason
 * `createTemplateNode` is (Task 26): the store instance a canvas is bound
 * to has to be supplied explicitly, not discovered via context.
 *
 * Brief: .tmp/flow-canvas-task-27-brief.md
 */

"use client";

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useStore, type StoreApi } from "zustand";
import Text from "@/refresh-components/texts/Text";
import { NodeFieldList } from "./NodeFieldList";
import { useComponentTemplates } from "../hooks/useComponentTemplates";
import type { FlowStore } from "../stores/flowStore";
import { findTemplateByType } from "../utils/findTemplate";

function PanelShell({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-testid="node-inspector"
      className="flex h-full w-80 shrink-0 flex-col gap-3 overflow-y-auto border-l border-canvas-border bg-canvas-panel p-3"
    >
      {children}
    </div>
  );
}

export function createNodeInspector(store: StoreApi<FlowStore>) {
  return function NodeInspector() {
    const { t } = useTranslation();
    const lastSelection = useStore(store, (s) => s.lastSelection);
    const nodes = useStore(store, (s) => s.nodes);
    const setNodes = useStore(store, (s) => s.setNodes);
    const takeSnapshot = useStore(store, (s) => s.takeSnapshot);
    const isInspectorOpen = useStore(store, (s) => s.isInspectorOpen);
    const { data: grouped, isLoading } = useComponentTemplates();
    // Debounced snapshots (27.6): one undo step per edit *session*, not
    // per keystroke. Snapshot lazily on a field's first change since its
    // last blur, then suppress further snapshots for that field until it
    // blurs again — mirrors Langflow's snapshot-on-blur/commit, not a
    // per-character history entry.
    const snapshottedFieldsRef = useRef<Set<string>>(new Set());

    const selectedNodeIds = lastSelection?.nodes.map((n) => n.id) ?? [];
    const selectedEdgeCount = lastSelection?.edges.length ?? 0;
    const totalSelected = selectedNodeIds.length + selectedEdgeCount;

    // Selecting a node must not summon this panel — upstream keeps it a
    // sticky preference toggled from the node toolbar
    // (`flowStore.inspectionPanelVisible`), and a panel that flies in on
    // every click makes the canvas feel unsteady. Fields stay editable on
    // the card itself either way, so nothing is unreachable while closed.
    if (!isInspectorOpen) {
      return null;
    }

    if (totalSelected === 0) {
      return null; // 27.2 — closes when selection is cleared
    }

    if (totalSelected > 1) {
      // 27.3 — a summary, never the first node's fields.
      return (
        <PanelShell>
          <Text mainUiBody className="font-medium">
            {t(
              "flowCanvas.inspector.itemsSelected",
              "{{count}} items selected",
              { count: totalSelected }
            )}
          </Text>
        </PanelShell>
      );
    }

    if (selectedEdgeCount === 1) {
      return (
        <PanelShell>
          <Text mainUiBody className="font-medium">
            {t(
              "flowCanvas.inspector.connectionSelected",
              "1 connection selected"
            )}
          </Text>
        </PanelShell>
      );
    }

    const nodeId = selectedNodeIds[0]!;
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return null;

    function handleFieldChange(key: string, value: unknown) {
      if (!snapshottedFieldsRef.current.has(key)) {
        takeSnapshot();
        snapshottedFieldsRef.current.add(key);
      }
      setNodes((current) =>
        current.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: { ...n.data, values: { ...n.data.values, [key]: value } },
              }
            : n
        )
      );
    }

    function handleFieldBlur(key: string) {
      snapshottedFieldsRef.current.delete(key);
    }

    if (isLoading) {
      return (
        <PanelShell>
          <div className="h-24 w-full animate-pulse rounded-08 bg-muted" />
        </PanelShell>
      );
    }

    const template = grouped
      ? findTemplateByType(grouped, node.data.type)
      : undefined;

    if (!template) {
      return (
        <PanelShell>
          <Text mainUiBody className="font-medium">
            {t(
              "flowCanvas.inspector.unknownComponent",
              "Unknown component: {{type}}",
              { type: node.data.type }
            )}
          </Text>
        </PanelShell>
      );
    }

    return (
      <PanelShell>
        <Text mainUiBody className="font-medium">
          {t(
            `flowCanvas.components.${template.type}.name`,
            template.display_name
          )}
        </Text>
        <NodeFieldList
          template={template}
          values={node.data.values}
          onFieldChange={handleFieldChange}
          onFieldBlur={handleFieldBlur}
        />
      </PanelShell>
    );
  };
}
