/**
 * Ported from Langflow (MIT) — src/frontend/src/types/flow/index.ts (concept only)
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 * Adapted for Onyx: values-only node data (design spec §4.4, R1) — Langflow
 * embeds the full component definition (its `APIClassType`, including
 * mutable field descriptors and Python code) inside every node's `data`.
 * Ours must not: a saved FlowSpec (P1 Task 1) stores `values` only, so a
 * template change on the backend can never silently invalidate a saved
 * flow. Any ported Langflow logic that reaches into
 * `node.data.node.template.*` has to be rewritten to look the
 * ComponentTemplate up from the registry by `node.data.type` instead.
 *
 * Brief: .tmp/flow-canvas-task-21-brief.md
 */

import type { Edge, Node, Viewport as XYViewport } from "@xyflow/react";

/**
 * Mirrors apps/agent-service/src/models/flows.py's PortType enum exactly —
 * string values included (backend serializes "Message", not "MESSAGE").
 * Governs which edges may connect (Task 22, handleTypes.ts).
 */
export type PortType =
  | "Message"
  | "Text"
  | "Documents"
  | "Tools"
  | "Model"
  | "Memory"
  | "Agent"
  | "Data"
  | "Trigger";

/** Canvas-side node data. The ComponentTemplate is looked up from the
 * registry by `type` at render time — never copied into the node. */
export type FlowNodeData = {
  type: string;
  templateVersion: number;
  values: Record<string, unknown>;
  /** Optional per-node description override, edited inline on the card. */
  description?: string;
};

export type CanvasNode = Node<FlowNodeData>;

/** sourceHandle/targetHandle carry plain port names (P1's Handle.name),
 * never Langflow-style JSON-encoded handle descriptors — our FlowEdge
 * already names source/target separately, so no id-encoding is needed. */
export type CanvasEdge = Edge;

export type Viewport = XYViewport;

/**
 * The wire format — mirrors apps/agent-service/src/models/flows.py's
 * FlowSpec/FlowNode/FlowEdge exactly, alias-for-alias. Verified against a
 * real `FlowSpec.model_dump(by_alias=True, mode="json")` call, not
 * hand-guessed: nodes serialize snake_case (`template_version`), edges
 * serialize camelCase (`sourceHandle`/`targetHandle`) — a deliberate
 * asymmetry (P1 Task 1: edges match @xyflow/react's own field names to
 * avoid a translation layer; nodes have no such upstream shape to match).
 */
export type WireFlowNode = {
  id: string;
  type: string;
  template_version: number;
  position: { x: number; y: number };
  values: Record<string, unknown>;
};

export type WireFlowEdge = {
  id: string;
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
};

export type WireFlowSpec = {
  version: string;
  nodes: WireFlowNode[];
  edges: WireFlowEdge[];
  viewport: Viewport | null;
};

/** Mirrors `ValidationIssue`/`_issue_dict` from
 * `domain/flows/validator.py` and `FlowVersionsRoute.py` — the shape both
 * `POST /validate-flow` and a 400 from `POST .../flow/publish` return.
 * Task 28. */
export type ValidationIssue = {
  code: string;
  message: string;
  node_id: string | null;
  edge_id: string | null;
};
