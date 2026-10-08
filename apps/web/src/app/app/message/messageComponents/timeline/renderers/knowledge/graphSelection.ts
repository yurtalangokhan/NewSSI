import type {
  EvidenceGraph,
  EvidenceGraphEdge,
} from "@/lib/api/domains/chat/knowledge-evidence-types";

/** What the reader picked in the graph: an entity or one relation. */
export type GraphSelection =
  | { kind: "node"; id: string }
  | { kind: "edge"; key: string }
  | null;

/** Edges have optional ids; the position makes every edge addressable. */
export function edgeKey(edge: EvidenceGraphEdge, index: number): string {
  return edge.id ?? `${edge.source}->${edge.target}#${index}`;
}

/** Whether a relation starts or ends at the entity. */
export function touchesNode(edge: EvidenceGraphEdge, nodeId: string): boolean {
  return edge.source === nodeId || edge.target === nodeId;
}

export interface KeyedEdge {
  edge: EvidenceGraphEdge;
  key: string;
}

/**
 * Relations with their keys, optionally only those touching one entity. Keys
 * come from each edge's position in the whole graph, so narrowing happens
 * after they are assigned.
 */
export function keyedEdges(
  graph: EvidenceGraph,
  nodeId: string | null = null
): KeyedEdge[] {
  return graph.edges
    .map((edge, index) => ({ edge, key: edgeKey(edge, index) }))
    .filter(({ edge }) => nodeId === null || touchesNode(edge, nodeId));
}

/** How many relations touch the entity. */
export function relationCount(graph: EvidenceGraph, nodeId: string): number {
  return keyedEdges(graph, nodeId).length;
}

export interface Highlight {
  nodes: ReadonlySet<string>;
  edges: ReadonlySet<string>;
}

/** Nodes and edges to emphasise for a selection; ``null`` when nothing is picked. */
export function highlightFor(
  graph: EvidenceGraph,
  selection: GraphSelection
): Highlight | null {
  if (selection === null) return null;
  const nodes = new Set<string>();
  const edges = new Set<string>();
  for (const { edge, key } of keyedEdges(graph)) {
    const touches =
      selection.kind === "node"
        ? touchesNode(edge, selection.id)
        : key === selection.key;
    if (touches) {
      edges.add(key);
      nodes.add(edge.source);
      nodes.add(edge.target);
    }
  }
  if (selection.kind === "node") nodes.add(selection.id);
  return { nodes, edges };
}

/** The entity whose details the side column shows for a selection. */
export function focusedNodeId(
  graph: EvidenceGraph,
  selection: GraphSelection
): string | null {
  if (selection?.kind === "node") return selection.id;
  if (selection?.kind === "edge") {
    const row = keyedEdges(graph).find(({ key }) => key === selection.key);
    return row?.edge.source ?? null;
  }
  return null;
}
