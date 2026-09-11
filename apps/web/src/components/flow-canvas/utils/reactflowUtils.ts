/**
 * Ported from Langflow (MIT) — src/frontend/src/utils/reactflowUtils.ts
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 * Adapted for Onyx: only `getNodeId` is ported in Task 21. Langflow's
 * `scapeJSONParse`/`scapedJSONStringfy` exist to encode a structured handle
 * descriptor (component id + field name) into a single string attribute —
 * our FlowEdge already carries `source`/`target`/`sourceHandle`/
 * `targetHandle` as separate plain-string fields (P1 Task 1), so no such
 * encoding is needed. Not porting them is a deliberate simplification, not
 * an oversight — see task-21-report.md.
 *
 * Brief: .tmp/flow-canvas-task-21-brief.md
 */

/**
 * A node id in the `{componentType}-{shortId}` shape — the same convention
 * the backend already uses for AgentRef subgraph node ids (P2 Task 12,
 * design spec amendment B), so ids look consistent whether a node was
 * created on the canvas or embedded server-side.
 */
export function getNodeId(componentType: string): string {
  const raw =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
  const shortId = raw.replace(/-/g, "").slice(0, 8);
  return `${componentType}-${shortId}`;
}
