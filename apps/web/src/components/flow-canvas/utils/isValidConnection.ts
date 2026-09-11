/**
 * Ported from Langflow (MIT) — src/frontend/src/utils/reactflowUtils.ts
 * (isValidConnection), concept only. Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Adapted for Onyx: Langflow's version reasons over its own
 * dataType/inputTypes/output_types handle-descriptor shape and additionally
 * implements loop-input cycle detection. Neither is ported:
 * - Type compatibility is Task 22's own handleTypes.ts, a direct mirror of
 *   the backend's handle_types.py — a different, simpler model (9-value
 *   PortType) than Langflow's.
 * - General-graph cycle detection is the backend validator's job at
 *   save/publish time (FLOW_ILLEGAL_CYCLE, P1 Task 3), with cycles only
 *   sanctioned through an explicit Loop node (R2). Reimplementing cycle
 *   detection here would duplicate that logic outside this task's
 *   anti-drift guarantee (handleTypes.test.ts 22.6) — deliberately not
 *   done. See task-22-report.md.
 *
 * What Langflow's version *does* have that this keeps: self-connection
 * rejection, duplicate-edge rejection, and target-handle occupancy (a
 * single-value input already fed by one edge does not silently accept a
 * second) — design spec §10's "illegal connection rejected in onConnect;
 * no request issued". Unlike Langflow, there's no per-field `list: true`
 * in this project's Handle model (types/componentTemplate.ts) — occupancy
 * is instead waived for the one PortType that's inherently multi-valued,
 * "Tools" (an agent takes any number of tool-providing components).
 *
 * Handle-type resolution is injected rather than fetched here, so this
 * module has no dependency on the component registry and is testable in
 * isolation (Task 24 supplies the real lookup, backed by Task 25/26's
 * registry fetch).
 *
 * Brief: .tmp/flow-canvas-task-22-brief.md
 */

import type { CanvasEdge, PortType } from "../types/flow";
import { handlesCompatible } from "./handleTypes";

export type Connection = {
  source: string | null;
  target: string | null;
  sourceHandle: string | null;
  targetHandle: string | null;
};

/** Resolves a node+handle to its declared PortType[], or null if the
 * handle/node/template can't be resolved. */
export type HandleTypeLookup = (
  nodeId: string,
  handleName: string,
  direction: "source" | "target"
) => PortType[] | null;

export function isValidConnection(
  connection: Connection,
  edges: CanvasEdge[],
  lookupHandleTypes: HandleTypeLookup
): boolean {
  const { source, target, sourceHandle, targetHandle } = connection;
  if (!source || !target || !sourceHandle || !targetHandle) return false;
  if (source === target) return false;

  const isDuplicate = edges.some(
    (e) =>
      e.source === source &&
      e.sourceHandle === sourceHandle &&
      e.target === target &&
      e.targetHandle === targetHandle
  );
  if (isDuplicate) return false;

  const sourceTypes = lookupHandleTypes(source, sourceHandle, "source");
  const targetTypes = lookupHandleTypes(target, targetHandle, "target");
  if (!sourceTypes || !targetTypes) return false;

  // "Tools" targets (an agent's tool input) are inherently multi-valued —
  // every tool-providing component wires into the same handle, so
  // single-value occupancy doesn't apply to them. No other PortType is
  // used as a list-shaped input today.
  const targetIsList = targetTypes.includes("Tools");
  if (!targetIsList) {
    const isTargetOccupied = edges.some(
      (e) => e.target === target && e.targetHandle === targetHandle
    );
    if (isTargetOccupied) return false;
  }

  return handlesCompatible(sourceTypes, targetTypes);
}
