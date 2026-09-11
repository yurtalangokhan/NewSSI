import type { NodeTypes } from "@xyflow/react";
import type { StoreApi } from "zustand";

import type { FlowStore } from "@/components/flow-canvas/stores/flowStore";
import { createNoteNode } from "@/components/flow-canvas/nodes/NoteNode";
import {
  NOTE_COMPONENT_TYPE,
  RendererNodeType,
} from "@/components/flow-canvas/nodes/nodeTypes";
import { createTemplateNode } from "@/components/flow-canvas/nodes/TemplateNode";

export {
  NOTE_COMPONENT_TYPE,
  RendererNodeType,
  rendererTypeForComponent,
} from "@/components/flow-canvas/nodes/nodeTypes";

/**
 * Build the `nodeTypes` map xyflow needs. One factory instead of the same
 * object literal rebuilt in FlowCanvas callers, InlineFlowDesigner,
 * FlowAgentPreview, GraphStageCanvas and FlowAgentEditorPage — adding a node
 * renderer is a one-line change here.
 */
export function createNodeTypes(
  store: StoreApi<FlowStore>,
  readOnly = false
): NodeTypes {
  const note = createNoteNode(store, readOnly);
  return {
    [RendererNodeType.Template]: createTemplateNode(store, readOnly),
    [RendererNodeType.Note]: note,
    // Legacy alias: some saved flows stored the renderer key as "note".
    [NOTE_COMPONENT_TYPE]: note,
  };
}
