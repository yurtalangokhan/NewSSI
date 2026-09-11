import type { StoreApi } from "zustand";
import { fromFlowSpec } from "./compile";
import type { WireFlowSpec } from "../types/flow";
import type { FlowStore } from "../stores/flowStore";

/** Fetches the backend's materialized subgraph for an existing agent and
 * merges it into the canvas at `position` — the "expand into flow" action
 * offered next to AgentRef once an agent is selected (design spec §7.4).
 * Reuses fromFlowSpec (the same WireFlowSpec -> CanvasNode/CanvasEdge
 * converter a loaded flow already goes through) and paste (the same
 * bulk-insert-with-id-remapping primitive copy/paste already uses) rather
 * than inventing a second canvas-mutation path. */
export async function expandAgentIntoFlow(
  agentId: string,
  store: StoreApi<FlowStore>,
  position: { x: number; y: number }
): Promise<void> {
  const response = await fetch(`/api/agent-definitions/${agentId}/expand`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Failed to expand agent: ${response.statusText}`);
  }
  const spec = (await response.json()) as WireFlowSpec;
  const { nodes, edges } = fromFlowSpec(spec);
  store.getState().paste({ nodes, edges }, position);
}
