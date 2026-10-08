"use client";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type Ref,
} from "react";
import { forceCollide, forceX, forceY } from "d3-force-3d";
import { useTheme } from "next-themes";
import { entityColor } from "@/lib/knowledge-graph/entityPalette";
import { escapeHtml } from "@/lib/text/escapeHtml";
import {
  glowByRank,
  glowStyle,
  linkEndId,
  neighborIds,
  toForceGraphData,
  type ForceGraphLink,
  type ForceGraphNode,
  type SourceGraph,
  type SourceGraphNode,
} from "@/lib/knowledge-graph/forceGraphModel";
import {
  LABEL_PRIORITY,
  isNodeLabeled,
  nodeLabelPriority,
  placeLabels,
  type LabelCandidate,
} from "@/lib/knowledge-graph/graphLabels";

/** Camera controls the surrounding toolbar drives. */
export interface KnowledgeForceGraphHandle {
  zoomBy: (factor: number) => void;
  fit: () => void;
}

interface KnowledgeForceGraphProps<N extends SourceGraphNode> {
  graph: SourceGraph<N>;
  height: number;
  selectedNodeId?: string | null;
  onSelectNode?: (node: N) => void;
  /** Off for previews: no zoom, pan, drag, tooltips, or clicks. */
  interactive?: boolean;
  ariaLabel: string;
  ref?: Ref<KnowledgeForceGraphHandle>;
}

type ForceGraph2DComponent = typeof import("react-force-graph-2d").default;

interface SimulationForce {
  strength(value: number): SimulationForce;
  distanceMax(value: number): SimulationForce;
  distance(value: number): SimulationForce;
}

/** The part of the force-graph instance API this view drives. */
interface ForceGraphInstance {
  d3Force(name: string): SimulationForce | undefined;
  d3Force(name: string, force: unknown): unknown;
  d3ReheatSimulation(): void;
  zoom(): number;
  zoom(scale: number, durationMs?: number): void;
  zoomToFit(durationMs?: number, paddingPx?: number): void;
  graph2ScreenCoords(x: number, y: number): { x: number; y: number };
}

// Screen-pixel sizes: labels stay readable at every zoom level.
const LABEL_FONT_PX = 11;
const EDGE_LABEL_FONT_PX = 9;
const LABEL_GAP_PX = 3;
// Space between a node and its label, and above an edge label, in screen px.
const EDGE_LABEL_LIFT_PX = 3;
const FIT_MS = 400;
const FIT_PADDING_PX = 40;
const ZOOM_MS = 200;
// Graph explorer's 2D force settings, plus a weak pull that keeps unrelated
// components from drifting apart.
const CHARGE = -180;
const CHARGE_RANGE = 500;
const LINK_DISTANCE = 55;
const COLLIDE_GAP = 12;
const GRAVITY = 0.08;

// Used when a design token is missing (before the theme stylesheet applies).
const FALLBACK_FONT = "sans-serif";
const FALLBACK_COLOR = {
  strong: "#111",
  muted: "#666",
  hotLink: "#444",
  link: "#ccc",
  dimLink: "#eee",
  background: "#fff",
  entity: "#888",
} as const;

// Node drawing, in graph units unless noted.
const DIMMED_ALPHA = 0.2;
const SELECTION_RING_ALPHA = 0.5;
const SELECTION_RING_GAP = 4;
const SELECTION_RING_WIDTH_PX = 2;
const UNMATCHED_OUTLINE_WIDTH = 1.6;
const LABEL_STROKE_WIDTH_PX = 3;
const LABEL_WEIGHT = { bold: "600", regular: "400" } as const;
// Links.
const HOT_LINK_WIDTH = 2;
const LINK_WIDTH = 1;
const LINK_ARROW_LENGTH = 3.5;
// Force simulation lifecycle.
const WARMUP_TICKS = 120;
const COOLDOWN_TICKS = 100;
const ALPHA_DECAY = 0.02;
const VELOCITY_DECAY = 0.3;

interface Palette {
  font: string;
  strong: string;
  muted: string;
  hotLink: string;
  link: string;
  dimLink: string;
  background: string;
}

function cssVar(name: string, fallback: string): string {
  return (
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() ||
    fallback
  );
}

function readPalette(): Palette {
  return {
    font: getComputedStyle(document.body).fontFamily || FALLBACK_FONT,
    strong: cssVar("--text-05", FALLBACK_COLOR.strong),
    muted: cssVar("--text-03", FALLBACK_COLOR.muted),
    hotLink: cssVar("--text-04", FALLBACK_COLOR.hotLink),
    link: cssVar("--border-02", FALLBACK_COLOR.link),
    dimLink: cssVar("--border-01", FALLBACK_COLOR.dimLink),
    background: cssVar("--background-neutral-00", FALLBACK_COLOR.background),
  };
}

interface PlacedLabel {
  text: string;
  x: number;
  y: number;
  fontSize: number;
  color: string;
  bold: boolean;
}

/**
 * A knowledge graph on a live force simulation, drawn the way the
 * graph explorer draws: hubs larger, labels screen-sized and placed without
 * collisions, the selection's neighborhood in focus and the rest dimmed.
 */
export default function KnowledgeForceGraph<N extends SourceGraphNode>({
  graph,
  height,
  selectedNodeId = null,
  onSelectNode,
  interactive = true,
  ariaLabel,
  ref,
}: KnowledgeForceGraphProps<N>) {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphInstance | undefined>(undefined);
  const fittedData = useRef<object | null>(null);
  const [ForceGraph2D, setForceGraph2D] =
    useState<ForceGraph2DComponent | null>(null);
  const [width, setWidth] = useState(0);
  const [palette, setPalette] = useState<Palette | null>(null);

  // The graph instance exists only once all of these are ready.
  const canDraw = ForceGraph2D !== null && palette !== null && width > 0;
  const data = useMemo(() => toForceGraphData(graph), [graph]);
  const neighbors = useMemo(
    () => neighborIds(graph, selectedNodeId),
    [graph, selectedNodeId]
  );
  const glow = useMemo(() => glowByRank(graph.nodes), [graph]);
  const colorOf = useMemo(() => {
    const cache = new Map<string, string>();
    return (label: string) => {
      let color = cache.get(label);
      if (color === undefined) {
        color = cssVar(
          `--theme-${entityColor(label)}-05`,
          FALLBACK_COLOR.entity
        );
        cache.set(label, color);
      }
      return color;
    };
    // Rebuilt with the palette: the CSS variables it reads change with the theme.
  }, [palette]);

  // Canvas cannot use CSS variables: resolve them in the browser, per theme.
  useEffect(() => {
    setPalette(readPalette());
  }, [resolvedTheme]);

  useEffect(() => {
    let alive = true;
    import("react-force-graph-2d").then((module) => {
      if (alive) setForceGraph2D(() => module.default);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setWidth(Math.floor(container.getBoundingClientRect().width));
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const simulation = graphRef.current;
    if (!simulation) return;
    simulation.d3Force("charge")?.strength(CHARGE).distanceMax(CHARGE_RANGE);
    simulation.d3Force("link")?.distance(LINK_DISTANCE);
    simulation.d3Force(
      "collide",
      forceCollide((node: ForceGraphNode) => node.radius + COLLIDE_GAP)
        .strength(1)
        .iterations(3)
    );
    simulation.d3Force("x", forceX(0).strength(GRAVITY));
    simulation.d3Force("y", forceY(0).strength(GRAVITY));
    simulation.d3ReheatSimulation();
  }, [data, canDraw]);

  useImperativeHandle(
    ref,
    () => ({
      zoomBy: (factor: number) => {
        const simulation = graphRef.current;
        if (simulation) simulation.zoom(simulation.zoom() * factor, ZOOM_MS);
      },
      fit: () => {
        graphRef.current?.zoomToFit(FIT_MS, FIT_PADDING_PX);
      },
    }),
    []
  );

  const handleEngineStop = useCallback(() => {
    // Fit once per result graph; later stops come from the user dragging.
    if (fittedData.current === data) return;
    fittedData.current = data;
    graphRef.current?.zoomToFit(FIT_MS, FIT_PADDING_PX);
  }, [data]);

  const isDimmed = useCallback(
    (nodeId: string) =>
      selectedNodeId !== null &&
      nodeId !== selectedNodeId &&
      !neighbors.has(nodeId),
    [selectedNodeId, neighbors]
  );

  const isHotLink = useCallback(
    (link: ForceGraphLink) =>
      selectedNodeId !== null &&
      (linkEndId(link.source) === selectedNodeId ||
        linkEndId(link.target) === selectedNodeId),
    [selectedNodeId]
  );

  const drawNode = useCallback(
    (
      node: ForceGraphNode,
      context: CanvasRenderingContext2D,
      scale: number
    ) => {
      if (!palette) return;
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const color = colorOf(node.label);
      const base = isDimmed(node.id) ? DIMMED_ALPHA : 1;
      const intensity = glow.get(node.id);
      if (intensity !== undefined && base === 1) {
        // Top RRF ranks glow; shadowBlur is in screen pixels, so the glow
        // looks the same at every zoom level.
        const halo = glowStyle(intensity);
        context.save();
        context.globalAlpha = halo.alpha;
        context.fillStyle = color;
        context.shadowColor = color;
        context.shadowBlur = halo.blur;
        context.beginPath();
        context.arc(x, y, node.radius + halo.haloExtra, 0, 2 * Math.PI);
        context.fill();
        context.restore();
      }
      if (node.id === selectedNodeId) {
        context.globalAlpha = SELECTION_RING_ALPHA;
        context.beginPath();
        context.arc(x, y, node.radius + SELECTION_RING_GAP, 0, 2 * Math.PI);
        context.strokeStyle = color;
        context.lineWidth = SELECTION_RING_WIDTH_PX / scale;
        context.stroke();
      }
      context.globalAlpha = base;
      context.beginPath();
      context.arc(x, y, node.radius, 0, 2 * Math.PI);
      if (node.matched) {
        context.fillStyle = color;
        context.fill();
      } else {
        context.fillStyle = palette.background;
        context.fill();
        context.strokeStyle = color;
        context.lineWidth = UNMATCHED_OUTLINE_WIDTH;
        context.stroke();
      }
      context.globalAlpha = 1;
    },
    [colorOf, glow, isDimmed, palette, selectedNodeId]
  );

  const drawLabels = useCallback(
    (context: CanvasRenderingContext2D, scale: number) => {
      const simulation = graphRef.current;
      if (!simulation || !palette || width === 0) return;
      const candidates: LabelCandidate[] = [];
      const placed = new Map<string, PlacedLabel>();
      const offset = (radius: number, fontPx: number) =>
        radius + (fontPx + LABEL_GAP_PX) / scale;

      for (const node of data.nodes) {
        if (node.x === undefined || node.y === undefined) continue;
        const focus = node.id === selectedNodeId || neighbors.has(node.id);
        if (
          !isNodeLabeled({
            matched: node.matched,
            inFocus: focus,
            hasSelection: selectedNodeId !== null,
            scale,
          })
        )
          continue;
        const y = node.y + offset(node.radius, LABEL_FONT_PX);
        const screen = simulation.graph2ScreenCoords(node.x, y);
        candidates.push({
          id: node.id,
          x: screen.x,
          baseline: screen.y,
          text: node.name,
          fontSize: LABEL_FONT_PX,
          priority: nodeLabelPriority(node, selectedNodeId, neighbors),
        });
        placed.set(node.id, {
          text: node.name,
          x: node.x,
          y,
          fontSize: LABEL_FONT_PX,
          color: node.matched ? palette.strong : palette.muted,
          bold: node.matched || node.id === selectedNodeId,
        });
      }

      for (const link of data.links) {
        if (!isHotLink(link)) continue;
        const source = link.source as ForceGraphNode;
        const target = link.target as ForceGraphNode;
        if (source.x === undefined || target.x === undefined) continue;
        const x = (source.x + target.x) / 2;
        const y =
          ((source.y ?? 0) + (target.y ?? 0)) / 2 - EDGE_LABEL_LIFT_PX / scale;
        const screen = simulation.graph2ScreenCoords(x, y);
        const id = `edge:${link.id}`;
        candidates.push({
          id,
          x: screen.x,
          baseline: screen.y,
          text: link.type,
          fontSize: EDGE_LABEL_FONT_PX,
          priority: LABEL_PRIORITY.selectedEdge,
        });
        placed.set(id, {
          text: link.type,
          x,
          y,
          fontSize: EDGE_LABEL_FONT_PX,
          color: palette.hotLink,
          bold: false,
        });
      }

      const visible = placeLabels(candidates, { width, height });
      context.save();
      context.textAlign = "center";
      context.textBaseline = "alphabetic";
      context.lineJoin = "round";
      placed.forEach((label, id) => {
        if (!visible.has(id)) return;
        const weight = label.bold ? LABEL_WEIGHT.bold : LABEL_WEIGHT.regular;
        context.font = `${weight} ${label.fontSize / scale}px ${palette.font}`;
        context.lineWidth = LABEL_STROKE_WIDTH_PX / scale;
        context.strokeStyle = palette.background;
        context.strokeText(label.text, label.x, label.y);
        context.fillStyle = label.color;
        context.fillText(label.text, label.x, label.y);
      });
      context.restore();
    },
    [data, height, isHotLink, neighbors, palette, selectedNodeId, width]
  );

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      data-testid="knowledge-graph-surface"
      style={{ height }}
    >
      {canDraw && ForceGraph2D && (
        <ForceGraph2D
          ref={graphRef}
          graphData={data}
          width={width}
          height={height}
          backgroundColor="transparent"
          nodeRelSize={1}
          nodeVal={(node: ForceGraphNode) => node.radius * node.radius}
          nodeLabel={(node: ForceGraphNode) =>
            `${escapeHtml(node.name)} (${escapeHtml(node.label)})`
          }
          nodeCanvasObject={drawNode}
          onNodeClick={(node: ForceGraphNode<N>) => onSelectNode?.(node.node)}
          enablePointerInteraction={interactive}
          enableZoomInteraction={interactive}
          enablePanInteraction={interactive}
          enableNodeDrag={interactive}
          linkLabel={(link: ForceGraphLink) => escapeHtml(link.type)}
          linkColor={(link: ForceGraphLink) =>
            isHotLink(link)
              ? palette.hotLink
              : selectedNodeId !== null
                ? palette.dimLink
                : palette.link
          }
          linkWidth={(link: ForceGraphLink) =>
            isHotLink(link) ? HOT_LINK_WIDTH : LINK_WIDTH
          }
          linkDirectionalArrowLength={LINK_ARROW_LENGTH}
          linkDirectionalArrowRelPos={1}
          onRenderFramePost={drawLabels}
          onEngineStop={handleEngineStop}
          cooldownTicks={COOLDOWN_TICKS}
          warmupTicks={WARMUP_TICKS}
          d3AlphaDecay={ALPHA_DECAY}
          d3VelocityDecay={VELOCITY_DECAY}
        />
      )}
    </div>
  );
}
