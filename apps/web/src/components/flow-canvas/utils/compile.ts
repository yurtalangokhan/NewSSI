/**
 * FlowSpec <-> xyflow round-trip. No direct Langflow equivalent — Langflow
 * serializes its own FlowType shape, which embeds full component
 * descriptors per node; ours is the values-only wire format the backend
 * defines (P1 Task 1, design spec §4.4, R1).
 *
 * Determinism is the whole point of this module: an unedited spec loaded
 * then saved must produce a byte-identical spec, or every autosave writes
 * a spurious new draft version (P3) and the version history fills with
 * noise. See compile.test.ts's 23.1 for the guarantee, checked against a
 * fixture generated directly from a real `FlowSpec.model_dump(...)` call,
 * not a hand-typed guess of the wire shape.
 *
 * Brief: .tmp/flow-canvas-task-23-brief.md
 */

import type {
  CanvasEdge,
  CanvasNode,
  Viewport,
  WireFlowEdge,
  WireFlowNode,
  WireFlowSpec,
} from "../types/flow";
import { rendererTypeForComponent } from "../nodes/nodeTypes";

const DEFAULT_VIEWPORT: Viewport = { x: 0, y: 0, zoom: 1 };

/** Sub-pixel drag drift must not look like an edit — round to whole pixels.
 * `+ 0` normalizes `-0` (e.g. Math.round(-0.0001) === -0) to `0`, since
 * `-0` and `0` are distinct under deep-equality but identical positions. */
function roundPosition(value: number): number {
  return Math.round(value) + 0;
}

export function fromFlowSpec(spec: WireFlowSpec): {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  viewport: Viewport;
} {
  const nodes: CanvasNode[] = spec.nodes.map((n) => ({
    id: n.id,
    // xyflow's own renderer-selection field (nodeTypes' key), distinct
    // from `data.type` below (this app's component type, e.g. "Chatbot").
    // Left unset here, xyflow can't match any registered nodeType and
    // silently renders nothing for the node — no error, no crash, just an
    // empty canvas despite the store holding valid data. `useCanvasWiring`'s
    // drop handler and `flowStore.addNote` already set this correctly for
    // nodes created on the canvas; loading a saved flow just never did.
    type: rendererTypeForComponent(n.type),
    position: { x: n.position.x, y: n.position.y },
    data: {
      type: n.type,
      templateVersion: n.template_version,
      values: n.values,
    },
  }));

  const edges: CanvasEdge[] = spec.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle,
    targetHandle: e.targetHandle,
  }));

  return { nodes, edges, viewport: spec.viewport ?? DEFAULT_VIEWPORT };
}

export function toFlowSpec(
  nodes: CanvasNode[],
  edges: CanvasEdge[],
  viewport: Viewport
): WireFlowSpec {
  // Sorted by id so selection/z-index-driven runtime reordering never
  // changes the serialized output (23.7) — xyflow reorders arrays as a
  // side effect of clicking a node, which must never look like an edit.
  const sortedNodes = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const sortedEdges = [...edges].sort((a, b) => a.id.localeCompare(b.id));

  const wireNodes: WireFlowNode[] = sortedNodes.map((n) => ({
    id: n.id,
    type: n.data.type,
    template_version: n.data.templateVersion,
    position: {
      x: roundPosition(n.position.x),
      y: roundPosition(n.position.y),
    },
    // Passed through verbatim — never filled in with a template default.
    // The backend resolves defaults (P1 Task 3's _resolved_value); baking
    // one in here would freeze today's default into the saved flow
    // forever, defeating template migrations (R1).
    values: n.data.values,
  }));

  const wireEdges: WireFlowEdge[] = sortedEdges.map((e) => ({
    id: e.id,
    source: e.source,
    // xyflow types these as `string | null | undefined` at rest, but a
    // connected edge always carries both — Task 22's isValidConnection
    // already rejects a connection missing either handle before an edge
    // can exist.
    sourceHandle: e.sourceHandle ?? "",
    target: e.target,
    targetHandle: e.targetHandle ?? "",
  }));

  return {
    version: "1.0",
    nodes: wireNodes,
    edges: wireEdges,
    viewport: {
      x: roundPosition(viewport.x),
      y: roundPosition(viewport.y),
      zoom: viewport.zoom,
    },
  };
}

/** Value-object keys that are presentation-only — changing them isn't a
 * change to what the flow *does*, so they're excluded from the diff
 * (design spec discussion: "yapısal + alan değişiklikleri", position and
 * sticky-note color explicitly called out as noise). Node `position` is
 * already excluded structurally, since the diff never looks at it. */
const IGNORED_VALUE_FIELDS = new Set(["color"]);

export type FlowDiffEntry =
  | { kind: "node-added"; nodeId: string; nodeType: string }
  | { kind: "node-removed"; nodeId: string; nodeType: string }
  | {
      kind: "edge-added";
      edgeId: string;
      sourceNodeId: string;
      sourceType: string;
      targetNodeId: string;
      targetType: string;
    }
  | {
      kind: "edge-removed";
      edgeId: string;
      sourceNodeId: string;
      sourceType: string;
      targetNodeId: string;
      targetType: string;
    }
  | {
      kind: "field-changed";
      nodeId: string;
      nodeType: string;
      field: string;
      oldValue: unknown;
      newValue: unknown;
    }
  | {
      kind: "template-upgraded";
      nodeId: string;
      nodeType: string;
      oldVersion: number;
      newVersion: number;
    };

function valuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function diffSortKey(entry: FlowDiffEntry): string {
  const id = "nodeId" in entry ? entry.nodeId : entry.edgeId;
  const field = entry.kind === "field-changed" ? entry.field : "";
  return `${id} ${field}`;
}

/** Compares two flow specs — a draft against the last published version,
 * or one historical version against another — and reports what changed
 * as a flat list of human-reviewable entries (version history's "what
 * did I actually change" list). Node/edge identity is their `id`, stable
 * across edits, so matching by id (not array position) is what makes
 * "added"/"removed"/"changed" meaningful rather than noise. Position and
 * a sticky note's color are deliberately not diffed — see
 * `IGNORED_VALUE_FIELDS`. Pure and synchronous: both specs are already
 * in hand (draft in the store, historical ones from
 * `getVersionDetail`) — no fetch belongs in here. */
export function diffFlowSpecs(
  oldSpec: WireFlowSpec,
  newSpec: WireFlowSpec
): FlowDiffEntry[] {
  const oldNodes = new Map(oldSpec.nodes.map((n) => [n.id, n]));
  const newNodes = new Map(newSpec.nodes.map((n) => [n.id, n]));
  const oldEdges = new Map(oldSpec.edges.map((e) => [e.id, e]));
  const newEdges = new Map(newSpec.edges.map((e) => [e.id, e]));

  const entries: FlowDiffEntry[] = [];

  // `for...of` over a Map/Set silently never runs a single iteration
  // under this project's `tsconfig.json` (`target: "es5"`, no
  // `downlevelIteration`) — TS's ES5 down-level transform indexes by
  // `.length`, which a Map/Set doesn't have, so the loop condition is
  // `0 < undefined` and the body just never executes. No error, no
  // warning — it silently produces an empty diff. `.forEach()` sidesteps
  // that transform entirely.
  oldNodes.forEach((oldNode, id) => {
    if (!newNodes.has(id)) {
      entries.push({
        kind: "node-removed",
        nodeId: id,
        nodeType: oldNode.type,
      });
    }
  });
  newNodes.forEach((newNode, id) => {
    if (!oldNodes.has(id)) {
      entries.push({ kind: "node-added", nodeId: id, nodeType: newNode.type });
    }
  });

  oldEdges.forEach((oldEdge, id) => {
    if (!newEdges.has(id)) {
      entries.push({
        kind: "edge-removed",
        edgeId: id,
        sourceNodeId: oldEdge.source,
        sourceType: oldNodes.get(oldEdge.source)?.type ?? oldEdge.source,
        targetNodeId: oldEdge.target,
        targetType: oldNodes.get(oldEdge.target)?.type ?? oldEdge.target,
      });
    }
  });
  newEdges.forEach((newEdge, id) => {
    if (!oldEdges.has(id)) {
      entries.push({
        kind: "edge-added",
        edgeId: id,
        sourceNodeId: newEdge.source,
        sourceType: newNodes.get(newEdge.source)?.type ?? newEdge.source,
        targetNodeId: newEdge.target,
        targetType: newNodes.get(newEdge.target)?.type ?? newEdge.target,
      });
    }
  });

  // Field/template-version changes only make sense for a node present on
  // both sides — a node that's purely added or removed already has its
  // own entry above, and diffing "nothing" against its values would just
  // fabricate a field-changed entry for every field it happens to have.
  oldNodes.forEach((oldNode, id) => {
    const newNode = newNodes.get(id);
    if (!newNode) return;

    if (oldNode.template_version !== newNode.template_version) {
      entries.push({
        kind: "template-upgraded",
        nodeId: id,
        nodeType: newNode.type,
        oldVersion: oldNode.template_version,
        newVersion: newNode.template_version,
      });
    }

    const fieldNames = new Set([
      ...Object.keys(oldNode.values ?? {}),
      ...Object.keys(newNode.values ?? {}),
    ]);
    fieldNames.forEach((field) => {
      if (IGNORED_VALUE_FIELDS.has(field)) return;
      const oldValue = oldNode.values?.[field];
      const newValue = newNode.values?.[field];
      if (!valuesEqual(oldValue, newValue)) {
        entries.push({
          kind: "field-changed",
          nodeId: id,
          nodeType: newNode.type,
          field,
          oldValue,
          newValue,
        });
      }
    });
  });

  return entries.sort((a, b) => diffSortKey(a).localeCompare(diffSortKey(b)));
}
