"use client";

import { useMemo } from "react";
import { computeGraphLayout } from "@/lib/knowledge-graph/layout";
import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";
import type {
  KnowledgeGraph,
  KnowledgeGraphNode,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import { neighborIds } from "@/lib/knowledge-graph/forceGraphModel";
import {
  nodeLabelPriority,
  placeLabels,
  type LabelCandidate,
} from "@/lib/knowledge-graph/graphLabels";

const MATCHED_RADIUS = 11;
const NEIGHBOR_RADIUS = 8;
const SELECTION_GAP = 6;
const LABEL_HALO = {
  paintOrder: "stroke",
  stroke: "var(--background-neutral-00)",
  strokeWidth: 4,
  strokeLinejoin: "round",
} as const;

interface KnowledgeGraphSvgProps {
  graph: KnowledgeGraph;
  width: number;
  height: number;
  /** Which node names may be drawn; only those that fit are. */
  labels: "all" | "matched" | "none";
  /** Font size of node labels in viewBox units. */
  labelSize?: number;
  selectedNodeId?: string | null;
  /** Makes nodes keyboard- and pointer-selectable. */
  onSelectNode?: (node: KnowledgeGraphNode) => void;
  ariaLabel: string;
}

function edgeKey(edge: KnowledgeGraph["edges"][number], index: number): string {
  return edge.id ?? `${edge.source}-${edge.type}-${edge.target}-${index}`;
}

function nodeRadius(node: KnowledgeGraphNode): number {
  return node.matched ? MATCHED_RADIUS : NEIGHBOR_RADIUS;
}

/**
 * A small knowledge subgraph drawn with a deterministic force layout: matched
 * entities are filled, neighbors are rings. Labels are placed by priority and
 * dropped where they would collide.
 */
export default function KnowledgeGraphSvg({
  graph,
  width,
  height,
  labels,
  labelSize = 12,
  selectedNodeId = null,
  onSelectNode,
  ariaLabel,
}: KnowledgeGraphSvgProps) {
  const layout = useMemo(
    () => computeGraphLayout(graph, { width, height, padding: 56 }),
    [graph, width, height]
  );
  const visibleLabels = useMemo(() => {
    const neighbors = neighborIds(graph, selectedNodeId);
    const candidates: LabelCandidate[] = [];
    for (const node of graph.nodes) {
      const drawable =
        labels === "all" || (labels === "matched" && node.matched);
      const point = layout.get(node.id);
      if (!drawable || !point) continue;
      candidates.push({
        id: node.id,
        x: point.x,
        baseline: point.y + nodeRadius(node) + labelSize + 3,
        text: node.name,
        fontSize: labelSize,
        priority: nodeLabelPriority(node, selectedNodeId, neighbors),
      });
    }
    return placeLabels(candidates, { width, height });
  }, [graph, layout, labels, labelSize, selectedNodeId, width, height]);
  const interactive = onSelectNode !== undefined;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role={interactive ? "group" : "img"}
      aria-label={ariaLabel}
      className="block h-auto w-full select-none"
    >
      {graph.edges.map((edge, index) => {
        const from = layout.get(edge.source);
        const to = layout.get(edge.target);
        if (!from || !to) return null;
        const hot =
          selectedNodeId !== null &&
          (edge.source === selectedNodeId || edge.target === selectedNodeId);
        return (
          <line
            key={edgeKey(edge, index)}
            data-testid="knowledge-search-edge"
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            style={{
              stroke: hot ? "var(--text-04)" : "var(--border-02)",
              strokeWidth: hot ? 2 : 1.4,
            }}
          />
        );
      })}

      {graph.nodes.map((node) => {
        const point = layout.get(node.id);
        if (!point) return null;
        const color = entityColorVar(entityColor(node.label), "05");
        const radius = nodeRadius(node);
        const selected = node.id === selectedNodeId;
        const select = () => onSelectNode?.(node);
        return (
          <g
            key={node.id}
            data-testid="knowledge-search-node"
            data-matched={node.matched}
            {...(interactive && {
              role: "button",
              tabIndex: 0,
              "aria-pressed": selected,
              "aria-label": `${node.name}, ${node.label}`,
              onClick: select,
              onKeyDown: (event: React.KeyboardEvent) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  select();
                }
              },
            })}
            className={
              interactive
                ? "cursor-pointer focus:outline-none [&:focus-visible>circle.core]:stroke-[var(--action-link-05)]"
                : undefined
            }
          >
            {selected && (
              <circle
                cx={point.x}
                cy={point.y}
                r={radius + SELECTION_GAP}
                style={{
                  fill: "none",
                  stroke: color,
                  strokeWidth: 2,
                  strokeOpacity: 0.5,
                }}
              />
            )}
            <circle
              className="core"
              cx={point.x}
              cy={point.y}
              r={radius}
              style={
                node.matched
                  ? { fill: color, stroke: "none" }
                  : {
                      fill: "var(--background-neutral-00)",
                      stroke: color,
                      strokeWidth: 2,
                    }
              }
            />
            {visibleLabels.has(node.id) && (
              <text
                x={point.x}
                y={point.y + radius + labelSize + 3}
                textAnchor="middle"
                className={
                  node.matched ? "font-secondary-action" : "font-secondary-body"
                }
                style={{
                  ...LABEL_HALO,
                  fontSize: labelSize,
                  fill: node.matched ? "var(--text-05)" : "var(--text-03)",
                }}
              >
                {node.name}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
