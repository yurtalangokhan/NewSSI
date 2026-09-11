/**
 * Shared canvas wiring between every mount point of the flow editor
 * (`FlowAgentEditorPage` for editing an existing flow-backed agent,
 * `InlineFlowDesigner` for designing one before it exists). Extracted so
 * both consumers resolve handle types and drop-created nodes identically
 * instead of maintaining two copies of the same closures.
 */

import { useCallback } from "react";
import type { XYPosition } from "@xyflow/react";
import type { StoreApi } from "zustand";
import type { FlowStore } from "@/components/flow-canvas/stores/flowStore";
import type { PortType } from "@/components/flow-canvas/types/flow";
import type { GroupedComponentTemplates } from "@/components/flow-canvas/types/componentTemplate";
import { recordRecentComponent } from "@/components/flow-canvas/hooks/useRecentComponents";
import { findTemplateByType } from "@/components/flow-canvas/utils/findTemplate";
import { getNodeId } from "@/components/flow-canvas/utils/reactflowUtils";
import { RendererNodeType } from "@/components/flow-canvas/nodes/nodeTypes";
import { getEffectiveOutputHandles } from "@/components/flow-canvas/utils/templateSchema";

export function useHandleTypeLookup(
  store: StoreApi<FlowStore>,
  grouped: GroupedComponentTemplates | undefined
) {
  return useCallback(
    (
      nodeId: string,
      handleName: string,
      direction: "source" | "target"
    ): PortType[] | null => {
      if (!grouped) return null;
      const node = store.getState().nodes.find((n) => n.id === nodeId);
      if (!node) return null;
      const template = findTemplateByType(grouped, node.data.type);
      if (!template) return null;
      const handles =
        direction === "source"
          ? getEffectiveOutputHandles(template, node.data.values)
          : template.handles.inputs;
      return (
        (handles.find((h) => h.name === handleName)?.types as
          | PortType[]
          | undefined) ?? null
      );
    },
    [grouped, store]
  );
}

export function useDropHandler(
  store: StoreApi<FlowStore>,
  grouped: GroupedComponentTemplates | undefined
) {
  return useCallback(
    (componentType: string, position: XYPosition) => {
      if (!grouped) return;
      const template = findTemplateByType(grouped, componentType);
      if (!template) return;
      recordRecentComponent(componentType);
      store.getState().takeSnapshot();
      store.getState().setNodes((current) => [
        ...current,
        {
          id: getNodeId(componentType),
          type: RendererNodeType.Template,
          position,
          data: {
            type: componentType,
            templateVersion: template.template_version,
            values: {},
          },
        },
      ]);
    },
    [grouped, store]
  );
}
