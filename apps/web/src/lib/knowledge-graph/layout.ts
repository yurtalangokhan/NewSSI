import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force-3d";

/** The structural shape a layout needs; evidence and search graphs both fit. */
export interface LayoutGraph {
  nodes: ReadonlyArray<{ id: string }>;
  edges: ReadonlyArray<{ source: string; target: string }>;
}

export interface GraphViewport {
  width: number;
  height: number;
  /** Space kept free around the drawing for node labels. */
  padding: number;
}

export interface Point {
  x: number;
  y: number;
}

interface SimNode {
  id: string;
  x: number;
  y: number;
}

const TICKS = 300;
// Unrelated components repel each other with nothing pulling them back, so a
// many-component graph spread far and shrank to specks when fit to the
// viewport. A weak pull toward the center plus a bounded repulsion range packs
// components together while connected nodes keep their link spacing.
const GRAVITY = 0.1;
const CHARGE_RANGE = 400;

/**
 * Deterministic force layout for a knowledge subgraph, scaled into the
 * padded viewport. Nodes start on a circle in input order and the simulation
 * runs a fixed number of ticks, so the same graph always draws the same way.
 */
export function computeGraphLayout(
  graph: LayoutGraph,
  viewport: GraphViewport
): Map<string, Point> {
  const center = { x: viewport.width / 2, y: viewport.height / 2 };
  const layout = new Map<string, Point>();
  if (graph.nodes.length === 0) return layout;
  if (graph.nodes.length === 1) {
    layout.set(graph.nodes[0]!.id, center);
    return layout;
  }

  const nodes: SimNode[] = graph.nodes.map((node, index) => {
    const angle = (2 * Math.PI * index) / graph.nodes.length;
    return { id: node.id, x: Math.cos(angle) * 100, y: Math.sin(angle) * 100 };
  });
  const links = graph.edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
  }));

  forceSimulation(nodes)
    .numDimensions(2)
    .force(
      "link",
      forceLink<SimNode, (typeof links)[number]>(links)
        .id((node) => node.id)
        .distance(120)
    )
    .force("charge", forceManyBody().strength(-420).distanceMax(CHARGE_RANGE))
    .force("collide", forceCollide(48))
    .force("center", forceCenter(0, 0))
    .force("x", forceX(0).strength(GRAVITY))
    .force("y", forceY(0).strength(GRAVITY))
    .stop()
    .tick(TICKS);

  return fitToViewport(nodes, viewport);
}

function fitToViewport(
  nodes: SimNode[],
  viewport: GraphViewport
): Map<string, Point> {
  const xs = nodes.map((node) => node.x);
  const ys = nodes.map((node) => node.y);
  const [minX, maxX, minY, maxY] = [
    Math.min(...xs),
    Math.max(...xs),
    Math.min(...ys),
    Math.max(...ys),
  ];
  const innerWidth = viewport.width - 2 * viewport.padding;
  const innerHeight = viewport.height - 2 * viewport.padding;
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const scale = Math.min(innerWidth / spanX, innerHeight / spanY);
  const offsetX = viewport.padding + (innerWidth - spanX * scale) / 2;
  const offsetY = viewport.padding + (innerHeight - spanY * scale) / 2;

  return new Map(
    nodes.map((node) => [
      node.id,
      {
        x: Math.round(offsetX + (node.x - minX) * scale),
        y: Math.round(offsetY + (node.y - minY) * scale),
      },
    ])
  );
}
