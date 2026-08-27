/**
 * Pure graph visualization helpers for GraphExplorer.
 * These are extracted from GraphExplorer.tsx to reduce file size.
 * All members are used only within GraphExplorer — no external consumers.
 */

import {
  isClusterNode,
  type ScalableNode,
  type GraphNode,
  type ClusteredGraphData,
  type GraphData,
} from "@/lib/langconnect";

// ── Color palette ──────────────────────────────────────────────────────────

export const LABEL_COLORS: Record<string, string> = {
  Person: "#4f46e5",
  Organization: "#0891b2",
  Location: "#059669",
  Event: "#d97706",
  Product: "#dc2626",
  Technology: "#7c3aed",
  Concept: "#2563eb",
  Document: "#64748b",
  Entity: "#6b7280",
};

export const CLUSTER_COLOR = "#d97706";
export const CLUSTER_BORDER_COLOR = "#f59e0b";
export const SELECTED_COLOR = "#f59e0b";

// ── Performance thresholds ─────────────────────────────────────────────────

export const POINTER_DISABLE_THRESHOLD = 2000;
export const FAST_COOLDOWN_THRESHOLD = 1000;
export const HIDE_LABELS_THRESHOLD = 3000;
export const LABEL_ZOOM_THRESHOLD = 0.7;

// ── Helpers ────────────────────────────────────────────────────────────────

export function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export function getLabelColor(label: string): string {
  return LABEL_COLORS[label] || `hsl(${hashString(label) % 360}, 60%, 50%)`;
}

export function getNodeColorExpanded(name: string, label: string): string {
  const baseHue = hashString(label) % 360;
  const offset = hashString(name) % 60;
  const hue = (baseHue + offset) % 360;
  const lightness = 40 + (hashString(name + "L") % 20);
  return `hsl(${hue}, 55%, ${lightness}%)`;
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface BreadcrumbItem {
  label: string;
  displayName: string;
  mode: "overview" | "expand" | "neighborhood" | "full";
  nodeId?: string;
}

export interface GraphExplorerProps {
  scalableData?: ClusteredGraphData | null;
  graphData?: GraphData | null;
  loading?: boolean;
  collectionId?: string | null;
  onNodeClick?: (node: GraphNode) => void;
  onClusterExpand?: (clusterLabel: string) => void;
  onNeighborhoodRequest?: (nodeId: string) => void;
  onBackToOverview?: () => void;
  selectedLabels?: Set<string>;
  selectedRelTypes?: Set<string>;
  isActive?: boolean;
  onLabelFacetCountsChange?: (items: { name: string; count: number }[]) => void;
  onRelTypeFacetCountsChange?: (
    items: { name: string; count: number }[]
  ) => void;
  onVisibleCountsChange?: (counts: {
    nodeCount: number;
    edgeCount: number;
  }) => void;
}

// ── Filtering helpers ───────────────────────────────────────────────────────

/**
 * Cluster/sub-cluster views never carry real edges (the backend summarizes
 * relationship info into each cluster node's `_rel_type_counts` instead of
 * returning edge records), so edge-derived filtering can't see them. Fall
 * back to that per-node aggregate for cluster nodes.
 */
export function clusterNodeMatchesRelTypes(
  n: ScalableNode,
  relSet: Set<string>
): boolean {
  if (!isClusterNode(n)) return false;
  const counts = n.properties?._rel_type_counts as
    | Record<string, number>
    | undefined;
  if (!counts) return false;
  return Object.keys(counts).some((rt) => relSet.has(rt));
}
