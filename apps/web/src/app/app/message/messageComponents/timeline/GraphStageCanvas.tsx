"use client";

import { useEffect, useMemo } from "react";
import { createFlowStore } from "@/components/flow-canvas/stores/flowStore";
import { useLoadFlowIntoStore } from "@/components/flow-canvas/hooks/useLoadFlowIntoStore";
import { useHandleTypeLookup } from "@/components/flow-canvas/hooks/useCanvasWiring";
import { useComponentTemplates } from "@/components/flow-canvas/hooks/useComponentTemplates";
import { createNodeTypes } from "@/components/flow-canvas/nodes/registry";
import { FlowEditorShell } from "@/components/flow-canvas/components/FlowEditorShell";
import { FlowCanvas } from "@/components/flow-canvas/FlowCanvas";
import type {
  NodeRunStatus,
  NodeExecutionData,
} from "@/components/flow-canvas/stores/flowStore";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";

export interface GraphStageCanvasProps {
  agentDefinitionId: string;
  /** The flow version_no this run executed, or null to show what is
   * currently published (runs predating version pinning). */
  pinnedVersionNo?: number | null;
  nodeRunStatus: Record<string, NodeRunStatus>;
  nodeExecutionData?: Record<string, NodeExecutionData>;
}

/** A compact, read-only rendering of a flow-backed agent's published graph,
 * embedded inline in the chat timeline (GraphStageStrip's "canvas" view) —
 * not the flow editor's own canvas, and deliberately without its chrome
 * (node/edge counts, edit link): just the diagram, live-highlighted by
 * whichever stage graph_stage_start/end packets say is running or done. */
export function GraphStageCanvas({
  agentDefinitionId,
  pinnedVersionNo,
  nodeRunStatus,
  nodeExecutionData,
}: GraphStageCanvasProps) {
  const store = useMemo(
    () => createFlowStore(),
    [agentDefinitionId, pinnedVersionNo]
  );
  const { data: grouped } = useComponentTemplates();
  const lookupHandleTypes = useHandleTypeLookup(store, grouped);
  const nodeTypes = useMemo(() => createNodeTypes(store, true), [store]);

  const { isLoading, error } = useLoadFlowIntoStore(agentDefinitionId, store, {
    source:
      pinnedVersionNo != null ? { versionNo: pinnedVersionNo } : "published",
  });

  useEffect(() => {
    store.getState().setNodeRunStatus(nodeRunStatus);
  }, [nodeRunStatus, store]);

  useEffect(() => {
    if (nodeExecutionData) {
      store.getState().setNodeExecutionData(nodeExecutionData);
    }
  }, [nodeExecutionData, store]);

  if (isLoading) {
    return (
      <div className="flex h-[28rem] w-full items-center justify-center rounded-12 border border-border-01 bg-background-tint-01">
        <SimpleLoader />
      </div>
    );
  }

  if (error) {
    return null;
  }

  return (
    <FlowEditorShell
      store={store}
      className="langflow-canvas relative h-[28rem] w-full overflow-hidden rounded-12 border border-border-01"
    >
      <FlowCanvas
        store={store}
        lookupHandleTypes={lookupHandleTypes}
        nodeTypes={nodeTypes}
        readOnly
        showMinimap={false}
      />
    </FlowEditorShell>
  );
}
