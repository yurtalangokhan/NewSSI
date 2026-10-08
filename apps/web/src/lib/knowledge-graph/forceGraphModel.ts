/**
 * The shape every knowledge graph shares — search results and chat evidence
 * alike — which is all the force view needs.
 */
export interface SourceGraphNode {
  id: string;
  name: string;
  label: string;
  matched: boolean;
  score?: number | null;
}

export interface SourceGraphEdge {
  id?: string | null;
  source: string;
  target: string;
  type: string;
}

export interface SourceGraph<N extends SourceGraphNode = SourceGraphNode> {
  nodes: readonly N[];
  edges: readonly SourceGraphEdge[];
}

/** A node as the force simulation sees it; the simulation adds x/y. */
export interface ForceGraphNode<N extends SourceGraphNode = SourceGraphNode> {
  id: string;
  name: string;
  label: string;
  matched: boolean;
  score: number | null;
  degree: number;
  radius: number;
  node: N;
  x?: number;
  y?: number;
}

/** The simulation replaces source/target ids with the node objects. */
export interface ForceGraphLink {
  id: string;
  source: string | ForceGraphNode;
  target: string | ForceGraphNode;
  type: string;
}

export interface ForceGraphData<N extends SourceGraphNode = SourceGraphNode> {
  nodes: ForceGraphNode<N>[];
  links: ForceGraphLink[];
}

const MATCHED_BASE_RADIUS = 6;
const NEIGHBOR_BASE_RADIUS = 4;
const MAX_DEGREE_BONUS = 4;

/** Hubs draw larger, as in the graph explorer: base plus a capped bonus. */
export function forceNodeRadius(matched: boolean, degree: number): number {
  const base = matched ? MATCHED_BASE_RADIUS : NEIGHBOR_BASE_RADIUS;
  return base + Math.min(MAX_DEGREE_BONUS, Math.sqrt(degree) * 0.8);
}

/** Fresh simulation objects for a result graph; the library mutates them. */
export function toForceGraphData<N extends SourceGraphNode>(
  graph: SourceGraph<N>
): ForceGraphData<N> {
  const degree = new Map<string, number>();
  for (const edge of graph.edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  return {
    nodes: graph.nodes.map((node) => {
      const nodeDegree = degree.get(node.id) ?? 0;
      return {
        id: node.id,
        name: node.name,
        label: node.label,
        matched: node.matched,
        score: node.score ?? null,
        degree: nodeDegree,
        radius: forceNodeRadius(node.matched, nodeDegree),
        node,
      };
    }),
    links: graph.edges.map((edge, index) => ({
      id: edge.id ?? `${edge.source}-${edge.type}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      type: edge.type,
    })),
  };
}

/**
 * Direct matches, strongest first: the graph search scores them by RRF;
 * neighbors reached through expansion have no score and are left out.
 */
export function rankedMatches<N extends SourceGraphNode>(
  nodes: readonly N[]
): N[] {
  return nodes
    .filter((node) => node.matched)
    .sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity));
}

/** How many of the best RRF-ranked matches glow. */
export const GLOW_TOP_RANKS = 10;
const MIN_GLOW = 0.35;

/** Glow intensity (1 = brightest) of the top RRF-ranked matches, in rank order. */
export function glowByRank(
  nodes: readonly SourceGraphNode[]
): Map<string, number> {
  const ranked = rankedMatches(nodes)
    .filter((node) => typeof node.score === "number")
    .slice(0, GLOW_TOP_RANKS);
  const step = ranked.length > 1 ? (1 - MIN_GLOW) / (ranked.length - 1) : 0;
  return new Map(ranked.map((node, rank) => [node.id, 1 - rank * step]));
}

// The halo of a top-ranked match, scaled by its glow intensity (0-1).
const GLOW_ALPHA_BASE = 0.25;
const GLOW_ALPHA_GAIN = 0.35;
const GLOW_BLUR_BASE_PX = 8;
const GLOW_BLUR_GAIN_PX = 16;
const GLOW_HALO_BASE = 2;
const GLOW_HALO_GAIN = 3;

export interface GlowStyle {
  /** Halo opacity. */
  alpha: number;
  /** Canvas shadow blur, in screen pixels. */
  blur: number;
  /** Halo radius beyond the node radius, in graph units. */
  haloExtra: number;
}

/** How a match with glow `intensity` (1 = brightest) is haloed. */
export function glowStyle(intensity: number): GlowStyle {
  return {
    alpha: GLOW_ALPHA_BASE + GLOW_ALPHA_GAIN * intensity,
    blur: GLOW_BLUR_BASE_PX + GLOW_BLUR_GAIN_PX * intensity,
    haloExtra: GLOW_HALO_BASE + GLOW_HALO_GAIN * intensity,
  };
}

/** Ids directly connected to `nodeId`, in either direction. */
export function neighborIds(
  graph: SourceGraph,
  nodeId: string | null
): Set<string> {
  const neighbors = new Set<string>();
  if (nodeId === null) return neighbors;
  for (const edge of graph.edges) {
    if (edge.source === nodeId) neighbors.add(edge.target);
    if (edge.target === nodeId) neighbors.add(edge.source);
  }
  return neighbors;
}

/** The id at one end of a link, before or after the simulation resolved it. */
export function linkEndId(end: string | ForceGraphNode): string {
  return typeof end === "string" ? end : end.id;
}
