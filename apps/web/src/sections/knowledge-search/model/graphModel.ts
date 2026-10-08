import type {
  KnowledgeFacetValue,
  KnowledgeGraph,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeNeighborhoodGroup,
  KnowledgeSearchHit,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

export interface NodeRelation {
  edge: KnowledgeGraphEdge;
  type: string;
  direction: "out" | "in";
  other: KnowledgeGraphNode;
}

function edgeIdentity(edge: KnowledgeGraphEdge): string {
  return edge.id ?? `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
}

/** Union two graphs; existing nodes keep their data but gain `matched`. */
export function mergeKnowledgeGraphs(
  base: KnowledgeGraph,
  extra: KnowledgeGraph
): KnowledgeGraph {
  const nodes = new Map(base.nodes.map((node) => [node.id, node]));
  for (const node of extra.nodes) {
    const existing = nodes.get(node.id);
    nodes.set(
      node.id,
      existing
        ? { ...existing, matched: existing.matched || node.matched }
        : node
    );
  }
  const seen = new Set<string>();
  const edges: KnowledgeGraphEdge[] = [];
  for (const edge of [...base.edges, ...extra.edges]) {
    const identity = edgeIdentity(edge);
    if (seen.has(identity)) continue;
    if (!nodes.has(edge.source) || !nodes.has(edge.target)) continue;
    seen.add(identity);
    edges.push(edge);
  }
  return { nodes: Array.from(nodes.values()), edges };
}

/** The nodes the predicate keeps, and the edges between them. */
export function inducedSubgraph(
  graph: KnowledgeGraph,
  keep: (node: KnowledgeGraphNode) => boolean
): KnowledgeGraph {
  const nodes = graph.nodes.filter(keep);
  const kept = new Set(nodes.map((node) => node.id));
  return {
    nodes,
    edges: graph.edges.filter(
      (edge) => kept.has(edge.source) && kept.has(edge.target)
    ),
  };
}

/** Only nodes the query matched, and the edges between them. */
export function matchedOnlyGraph(graph: KnowledgeGraph): KnowledgeGraph {
  return inducedSubgraph(graph, (node) => node.matched);
}

/**
 * Only nodes of the chosen entity labels and the edges between them; the
 * server filters the result graph the same way, this also covers neighbors
 * merged in by depth expansion.
 */
export function entityLabelGraph(
  graph: KnowledgeGraph,
  labels: readonly string[]
): KnowledgeGraph {
  if (labels.length === 0) return graph;
  const wanted = new Set(labels.map((label) => label.toLocaleLowerCase()));
  return inducedSubgraph(graph, (node) =>
    wanted.has(node.label.toLocaleLowerCase())
  );
}

/** A node's relations with the node on the other end. */
export function relationsOf(
  graph: KnowledgeGraph,
  nodeId: string
): NodeRelation[] {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const relations: NodeRelation[] = [];
  for (const edge of graph.edges) {
    const direction =
      edge.source === nodeId ? "out" : edge.target === nodeId ? "in" : null;
    if (direction === null) continue;
    const other = nodes.get(direction === "out" ? edge.target : edge.source);
    if (other) relations.push({ edge, type: edge.type, direction, other });
  }
  return relations;
}

/** Node labels in the graph, most frequent first. */
export function entityLabelCounts(
  graph: KnowledgeGraph
): KnowledgeFacetValue[] {
  const counts = new Map<string, number>();
  for (const node of graph.nodes) {
    counts.set(node.label, (counts.get(node.label) ?? 0) + 1);
  }
  return Array.from(counts, ([value, count]) => ({ value, count })).sort(
    (a, b) => b.count - a.count || a.value.localeCompare(b.value)
  );
}

/** Deepest hop count "expand neighbors" may reach for one node. */
export const MAX_NODE_EXPANSION_DEPTH = 3;

/** Most seed nodes one neighborhood request may expand. */
export const MAX_EXPANSION_NODES = 20;

/** Matched node ids per collection, for depth expansion requests. */
export function matchedNodesByCollection(
  graph: KnowledgeGraph
): KnowledgeNeighborhoodGroup[] {
  const groups = new Map<string, string[]>();
  for (const node of graph.nodes) {
    if (!node.matched) continue;
    const ids = groups.get(node.collectionId) ?? [];
    if (ids.length < MAX_EXPANSION_NODES) ids.push(node.id);
    groups.set(node.collectionId, ids);
  }
  return Array.from(groups, ([collectionId, nodeIds]) => ({
    collectionId,
    nodeIds,
  }));
}

/** The graph node behind an entity hit, for when the graph omits it. */
export function nodeFromEntityHit(
  hit: KnowledgeSearchHit
): KnowledgeGraphNode | undefined {
  const entity = hit.entity;
  if (!entity) return undefined;
  return {
    id: entity.nodeId,
    name: entity.name,
    label: entity.label,
    matched: entity.matched,
    score: hit.score,
    collectionId: hit.collectionId,
    properties: entity.properties,
  };
}
