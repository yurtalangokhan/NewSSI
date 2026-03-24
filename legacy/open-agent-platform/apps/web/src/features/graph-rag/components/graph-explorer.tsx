/**
 * Interactive force-directed graph visualization with scalable rendering.
 *
 * Supports:
 * - 2D (react-force-graph-2d) and 3D (react-force-graph-3d) modes
 * - Supernode clustering for large graphs (click-to-expand)
 * - Level-of-Detail rendering (labels only at high zoom)
 * - Adaptive performance (pointer interaction toggle, warmup ticks)
 * - Neighborhood exploration (ego-graph on right-click)
 * - Breadcrumb navigation for drill-down
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  forceCollide as d3ForceCollide,
} from "d3-force-3d";
import dynamic from "next/dynamic";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Box,
  ChevronRight,
  Layers,
  Loader2,
  Maximize2,
  Minimize2,
  Search,
  Square,
  ZoomIn,
  ZoomOut,
  RotateCcw,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { GraphData, GraphNode, ClusteredGraphData, ScalableNode, ScalableEdge } from "@/types/graph";
import { isClusterNode, isClusterEdge } from "@/types/graph";
import type { ForceGraphData, ForceGraphNode, ForceGraphLink } from "@/types/graph";

// Lazy-load 3D renderer at module level with SSR disabled.
// Three.js accesses WebGL constants (VERTEX etc.) at import time which
// crashes in Node/SSR.  next/dynamic with ssr:false ensures the module
// is only ever evaluated in the browser.
const ForceGraph3DLazy = dynamic(
  () => import("./force-graph-3d-wrapper"),
  { ssr: false, loading: () => <Skeleton className="h-[300px] w-full rounded-lg" /> },
);

// Color palette for different entity labels
const LABEL_COLORS: Record<string, string> = {
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

function getLabelColor(label: string): string {
  return LABEL_COLORS[label] || `hsl(${hashString(label) % 360}, 60%, 50%)`;
}

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

/**
 * When all nodes share the same label (e.g. after expanding a "Person" cluster)
 * derive colour from the node *name* so each entity is visually distinct.
 */
function getNodeColorExpanded(name: string, label: string): string {
  const baseHue = hashString(label) % 360;
  const nameOffset = hashString(name) % 60; // ±30° spread around base
  const hue = (baseHue + nameOffset) % 360;
  const lightness = 40 + (hashString(name + "L") % 20); // 40-60%
  return `hsl(${hue}, 55%, ${lightness}%)`;
}

// Cluster supernodes get distinct styling
const CLUSTER_COLOR = "#d97706";
const CLUSTER_BORDER_COLOR = "#f59e0b";
const SELECTED_COLOR = "#f59e0b";

// Performance thresholds
const POINTER_DISABLE_THRESHOLD = 2000;
const FAST_COOLDOWN_THRESHOLD = 1000;
const HIDE_LABELS_THRESHOLD = 3000;
const LABEL_ZOOM_THRESHOLD = 0.7;

// Breadcrumb for drill-down navigation
interface BreadcrumbItem {
  label: string;
  displayName: string;
  mode: "overview" | "expand" | "neighborhood" | "full";
  nodeId?: string;
}

interface GraphExplorerProps {
  /** Standard graph data (legacy mode) */
  graphData?: GraphData | null;
  /** Scalable clustered graph data */
  scalableData?: ClusteredGraphData | null;
  loading?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  /** Callback when a cluster supernode is clicked (drill-down) */
  onClusterExpand?: (clusterLabel: string) => void;
  /** Callback for neighborhood exploration */
  onNeighborhoodRequest?: (nodeId: string) => void;
  /** Callback to go back to overview */
  onBackToOverview?: () => void;
  /** Filter graph to only show nodes with these labels */
  selectedLabels?: Set<string>;
  /** Filter graph to only show edges with these relationship types */
  selectedRelTypes?: Set<string>;
  /** Server-side cluster search — returns {label: matchCount} for clusters
   *  that contain entities matching the query. */
  onSearchNodes?: (query: string) => Promise<Record<string, number> | null>;
}

export function GraphExplorer({
  graphData,
  scalableData,
  loading,
  onNodeClick,
  onClusterExpand,
  onNeighborhoodRequest,
  onBackToOverview,
  selectedLabels,
  selectedRelTypes,
  onSearchNodes,
}: GraphExplorerProps) {
  const fgRef = useRef<any>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const [ForceGraph2D, setForceGraph2D] = useState<any>(null);
  const [is3D, setIs3D] = useState(false);
  const [threeDKey, setThreeDKey] = useState(0); // increment to force 3D remount
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 800, height: 700 });
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);

  // ── Simulation settling — overlay while force layout stabilizes ──
  const [settling, setSettling] = useState(true);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prevDataFingerprintRef = useRef("");

  // Server-side cluster search results: label → match count
  const [serverClusterMatches, setServerClusterMatches] = useState<Record<string, number> | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Matched cluster labels from server search
  const serverMatchedClusterLabels = useMemo(() => {
    if (!serverClusterMatches) return new Map<string, number>();
    return new Map(Object.entries(serverClusterMatches));
  }, [serverClusterMatches]);

  // Only use scalableData for visualization to prevent flashing normal nodes before clustered nodes load
  const activeData = scalableData;
  const currentMode = scalableData?.mode || "full";
  const totalNodes = scalableData?.total_node_count ?? graphData?.nodes.length ?? 0;
  const totalEdges = scalableData?.total_edge_count ?? graphData?.edges.length ?? 0;

  // Dynamic import of react-force-graph-2d (always loaded)
  useEffect(() => {
    import("react-force-graph-2d").then((mod) => {
      setForceGraph2D(() => mod.default);
    });
  }, []);

  // Callback ref — fires every time the DOM node mounts / unmounts.
  // This guarantees the ResizeObserver is attached the moment the real
  // card appears (after loading finishes), not before.
  const containerRef = useCallback((node: HTMLDivElement | null) => {
    // tear down previous observer
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
    if (!node) return;

    // initial measurement
    const w = node.clientWidth;
    const h = node.clientHeight;
    if (w > 0 && h > 0) {
      setDimensions({ width: w, height: h });
    }

    // observe future resizes (fullscreen toggle, window resize, etc.)
    const ro = new ResizeObserver(() => {
      const rw = node.clientWidth;
      const rh = node.clientHeight;
      if (rw > 0 && rh > 0) {
        setDimensions((prev) =>
          prev.width === rw && prev.height === rh
            ? prev
            : { width: rw, height: rh },
        );
      }
    });
    ro.observe(node);
    observerRef.current = ro;
  }, []);

  // Clean up observer on unmount
  useEffect(() => {
    return () => observerRef.current?.disconnect();
  }, []);

  // Convert data → ForceGraphData (handles both standard and clustered)
  const forceData: ForceGraphData = useMemo(() => {
    if (!activeData) return { nodes: [], links: [] };

    const rawNodes: ScalableNode[] = "nodes" in activeData ? activeData.nodes : [];
    const rawEdges: ScalableEdge[] = "edges" in activeData ? activeData.edges : [];

    const hasLabelFilter = selectedLabels && selectedLabels.size > 0;
    const hasRelFilter = selectedRelTypes && selectedRelTypes.size > 0;

    // ── Build filtered node & edge sets ────────────────────────────
    // When BOTH label and relationship-type filters are active we need
    // a combined strategy:
    //   1. Find edges whose type is in selectedRelTypes AND that touch
    //      at least one node whose label is in selectedLabels.
    //   2. Keep all nodes on both ends of those surviving edges.
    // This ensures cross-label relationships (e.g. Person --WORKS_AT-->
    // Organization) still render even when only one label is selected.

    let filteredNodes: ScalableNode[];
    let filteredEdges: ScalableEdge[];

    if (hasLabelFilter && hasRelFilter) {
      // Both filters active — combined approach
      const labelSet = selectedLabels;
      const relSet = selectedRelTypes;
      const nodeMap = new Map(rawNodes.map((n) => [n.id, n]));

      // Edges that match the rel-type filter AND touch at least one
      // node with a selected label.
      filteredEdges = rawEdges.filter((e) => {
        const typeMatches = isClusterEdge(e)
          ? e.relationship_types.some((rt) => relSet.has(rt))
          : relSet.has(e.type);
        if (!typeMatches) return false;

        const srcNode = nodeMap.get(e.source);
        const tgtNode = nodeMap.get(e.target);
        return (
          (srcNode && labelSet.has(srcNode.label)) ||
          (tgtNode && labelSet.has(tgtNode.label))
        );
      });

      // Nodes on either end of a surviving edge
      const connectedIds = new Set<string>();
      for (const e of filteredEdges) {
        connectedIds.add(e.source);
        connectedIds.add(e.target);
      }
      filteredNodes = rawNodes.filter((n) => {
        if (connectedIds.has(n.id)) return true;
        // Keep cluster nodes if their overall statistics show they participate in the selected relationships
        if (isClusterNode(n) && n.properties?._rel_type_counts) {
          const counts = n.properties._rel_type_counts as Record<string, number>;
          const hasRel = Array.from(relSet).some((rt) => (counts[rt] || 0) > 0);
          return hasRel && labelSet.has(n.label);
        }
        return false;
      });
    } else if (hasRelFilter) {
      // Only relationship-type filter
      filteredEdges = rawEdges.filter((e) => {
        if (isClusterEdge(e)) {
          return e.relationship_types.some((rt) => selectedRelTypes.has(rt));
        }
        return selectedRelTypes.has(e.type);
      });
      const connectedIds = new Set<string>();
      for (const e of filteredEdges) {
        connectedIds.add(e.source);
        connectedIds.add(e.target);
      }
      filteredNodes = rawNodes.filter((n) => {
        if (connectedIds.has(n.id)) return true;
        // Keep cluster nodes if their overall statistics show they participate in the selected relationships
        if (isClusterNode(n) && n.properties?._rel_type_counts) {
          const counts = n.properties._rel_type_counts as Record<string, number>;
          return Array.from(selectedRelTypes).some((rt) => (counts[rt] || 0) > 0);
        }
        return false;
      });
    } else if (hasLabelFilter) {
      // Only label filter
      filteredNodes = rawNodes.filter((n) => selectedLabels.has(n.label));
      const nodeIds = new Set(filteredNodes.map((n) => n.id));
      filteredEdges = rawEdges.filter(
        (e) => nodeIds.has(e.source) && nodeIds.has(e.target),
      );
    } else {
      // No filters
      filteredNodes = rawNodes;
      filteredEdges = rawEdges;
    }

    const nodes: ForceGraphNode[] = filteredNodes.map((n) => {
      if (isClusterNode(n)) {
        return {
          id: n.id,
          name: n.name,
          label: n.label,
          val: Math.max(5, Math.min(30, Math.sqrt(n.node_count) * 2)),
          color: CLUSTER_COLOR,
          properties: n.properties,
          isCluster: true,
          nodeCount: n.node_count,
          topEntities: n.top_entities,
        };
      }
      // In expanded / neighborhood views all nodes share the same label,
      // so derive colour from node name for visual diversity.
      const useNameColor = currentMode === "expand" || currentMode === "neighborhood";
      return {
        id: n.id,
        name: n.name,
        label: n.label,
        val: 3,
        color: useNameColor ? getNodeColorExpanded(n.name, n.label) : getLabelColor(n.label),
        properties: (n as any).properties,
      };
    });

    const links: ForceGraphLink[] = filteredEdges.map((e) => {
      if (isClusterEdge(e)) {
        return {
          source: e.source,
          target: e.target,
          type: e.type,
          color: "#94a3b8",
          weight: e.weight,
          relationshipTypes: e.relationship_types,
        };
      }
      return {
        source: e.source,
        target: e.target,
        type: e.type,
        color: "#94a3b8",
      };
    });

    return { nodes, links };
  }, [activeData, selectedLabels, selectedRelTypes, currentMode]);

  // ── Trigger settling overlay when graph data fundamentally changes ──
  useEffect(() => {
    const fp = `${scalableData?.mode}-${forceData.nodes.length}-${scalableData?.scope_label}`;
    if (fp !== prevDataFingerprintRef.current && forceData.nodes.length > 0) {
      prevDataFingerprintRef.current = fp;
      setSettling(true);
      clearTimeout(settleTimerRef.current);
      // Safety timeout — show graph even if onEngineStop never fires
      settleTimerRef.current = setTimeout(() => setSettling(false), 2500);
    }
    return () => clearTimeout(settleTimerRef.current);
  }, [forceData, scalableData?.mode, scalableData?.scope_label]);

  // Called when the force simulation finishes cooling down
  const handleEngineStop = useCallback(() => {
    clearTimeout(settleTimerRef.current);
    setSettling(false);
  }, []);

  // ── Debounced server-side cluster search ──
  // When the view contains cluster nodes, ask the server which clusters
  // contain entities matching the query. Does NOT break clusters apart.
  const hasClusterNodes = useMemo(
    () => forceData.nodes.some((n) => n.isCluster),
    [forceData],
  );
  useEffect(() => {
    clearTimeout(searchDebounce.current);
    if (!searchQuery.trim() || !hasClusterNodes) {
      setServerClusterMatches(null);
      setSearchLoading(false);
      return;
    }
    if (!onSearchNodes) return;
    setSearchLoading(true);
    searchDebounce.current = setTimeout(async () => {
      const results = await onSearchNodes(searchQuery);
      setServerClusterMatches(results);
      setSearchLoading(false);
    }, 400);
    return () => clearTimeout(searchDebounce.current);
  }, [searchQuery, hasClusterNodes, onSearchNodes]);

  // Filter by search (supports cluster topEntities + server cluster matches)
  const filteredData: ForceGraphData = useMemo(() => {
    if (!searchQuery.trim()) return forceData;
    const q = searchQuery.toLowerCase();
    const matchedNodes = forceData.nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.label.toLowerCase().includes(q) ||
        (n.topEntities && n.topEntities.some((e) => e.toLowerCase().includes(q))) ||
        // Highlight clusters whose label appears in server search results
        (n.isCluster && (serverMatchedClusterLabels.has(n.label) || serverMatchedClusterLabels.has(n.id))),
    );
    const matchedIds = new Set(matchedNodes.map((n) => n.id));
    const connectedLinks = forceData.links.filter((l) => {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      return matchedIds.has(src) || matchedIds.has(tgt);
    });
    const connectedNodeIds = new Set<string>();
    connectedLinks.forEach((l) => {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      connectedNodeIds.add(src);
      connectedNodeIds.add(tgt);
    });
    const allRelevantNodes = forceData.nodes.filter(
      (n) => matchedIds.has(n.id) || connectedNodeIds.has(n.id),
    );
    return { nodes: allRelevantNodes, links: connectedLinks };
  }, [forceData, searchQuery, serverMatchedClusterLabels]);

  // ── Degree map — how many links each node has ──
  const degreeMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const l of filteredData.links) {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      map.set(src, (map.get(src) || 0) + 1);
      map.set(tgt, (map.get(tgt) || 0) + 1);
    }
    return map;
  }, [filteredData]);

  // ── Parallel link detection — tiny offset so overlapping links separate ──
  const parallelLinkMeta = useMemo(() => {
    const pairCount = new Map<string, number>();
    const pairIndex = new Map<string, number>();
    // Count how many links share the same source-target pair
    for (const l of filteredData.links) {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      const key = src < tgt ? `${src}||${tgt}` : `${tgt}||${src}`;
      pairCount.set(key, (pairCount.get(key) || 0) + 1);
    }
    // Assign per-link curvature (only for truly parallel edges)
    const curvatures = new Map<number, number>();
    filteredData.links.forEach((l, idx) => {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      const key = src < tgt ? `${src}||${tgt}` : `${tgt}||${src}`;
      const count = pairCount.get(key) || 1;
      if (count <= 1) {
        curvatures.set(idx, 0);
      } else {
        const i = pairIndex.get(key) || 0;
        pairIndex.set(key, i + 1);
        // Very subtle curvature so lines look almost straight but separate
        const sign = i % 2 === 0 ? 1 : -1;
        const magnitude = 0.04 + Math.floor(i / 2) * 0.04;
        curvatures.set(idx, sign * magnitude);
      }
    });
    return curvatures;
  }, [filteredData]);

  // ── Connected neighbours of the selected node ──
  const selectedNeighborIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const ids = new Set<string>();
    ids.add(selectedNodeId);
    for (const l of filteredData.links) {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      if (src === selectedNodeId) ids.add(tgt);
      if (tgt === selectedNodeId) ids.add(src);
    }
    return ids;
  }, [selectedNodeId, filteredData]);

  // ── Adaptive performance settings ──
  const nodeCount = filteredData.nodes.length;
  const linkCount = filteredData.links.length;
  const enablePointer = nodeCount < POINTER_DISABLE_THRESHOLD;
  const cooldownTicks = nodeCount > FAST_COOLDOWN_THRESHOLD ? 50 : 100;
  const warmupTicks = nodeCount > FAST_COOLDOWN_THRESHOLD ? 80 : 120;
  const showLabels = nodeCount < HIDE_LABELS_THRESHOLD;
  // Reduce visual density for graphs with many edges
  const isDense = linkCount > nodeCount * 3;

  // ── Configure d3 force simulation — anti-overlap ──
  // Uses setTimeout to ensure the new force-graph component has mounted
  // after a 2D↔3D toggle (fgRef.current is set after render).
  useEffect(() => {
    const applyForces = () => {
      if (!fgRef.current) return;
      const fg = fgRef.current;

      // 1. Charge repulsion — stronger in 3D since depth compresses visually
      const chargeStrength = is3D
        ? (isDense ? -500 : -350)
        : (isDense ? -300 : -180);
      const distMax = is3D ? 800 : 500;
      fg.d3Force("charge")?.strength(chargeStrength).distanceMax(distMax);

      // 2. Link distance — longer in 3D so nodes don't overlap visually
      const baseDist = is3D
        ? (isDense ? 140 : 100)
        : (isDense ? 80 : 55);
      fg.d3Force("link")?.distance(baseDist);

      // 3. Node collision force — bigger radius in 3D
      const extraBuffer = is3D ? 8 : 0;
      const collide = d3ForceCollide()
        .radius((node: any) => {
          // Skip link-midpoint virtual nodes — they use a separate collision
          if (node.__linkMid) return (node.__linkMidR || 4) + (is3D ? 4 : 0);
          if (node.isCluster) {
            const size = Math.max(8, Math.min(24, Math.sqrt(node.nodeCount || 10) * 2.5));
            return size + 10 + extraBuffer;
          }
          const deg = degreeMap.get(node.id) || 0;
          const baseR = isDense ? 4 : 5;
          const r = baseR + Math.min(4, Math.sqrt(deg) * 0.8);
          return r + 12 + extraBuffer; // generous buffer to keep links away from nodes
        })
        .strength(1.0)
        .iterations(5);
      fg.d3Force("collide", collide);

      // 4. Center gravity — keep graph compact
      fg.d3Force("center")?.strength(1);

      // 5. No radial
      fg.d3Force("radial", null);

      // Reheat simulation so new forces take effect
      fg.d3ReheatSimulation?.();
    };

    // Immediate attempt + delayed retry for 2D↔3D toggle
    applyForces();
    const timer = setTimeout(applyForces, 200);
    return () => clearTimeout(timer);
  }, [isDense, filteredData, degreeMap, is3D]);

  const handleNodeClick = useCallback(
    (node: any) => {
      setSelectedNodeId(node.id);

      // Cluster supernode → drill down
      if (node.isCluster && onClusterExpand) {
        // Clear selection so expanded nodes don't appear dimmed
        setSelectedNodeId(null);
        setHoveredNodeId(null);
        // Pause animation before data change to prevent tick crash in 3D
        if (fgRef.current) {
          try { fgRef.current.pauseAnimation?.(); } catch { /* noop */ }
        }
        // Sub-clusters encode offset in the ID (subcluster__Label__skip__limit)
        // Top-level clusters use the label as identifier
        const expandId = typeof node.id === "string" && node.id.startsWith("subcluster__")
          ? node.id
          : node.label;
        setBreadcrumbs((prev) => [
          ...prev,
          { label: expandId, displayName: node.name, mode: "expand" },
        ]);
        onClusterExpand(expandId);
        return;
      }

      // Normal node → fire onNodeClick
      if (onNodeClick && graphData) {
        const gNode = graphData.nodes.find((n) => n.id === node.id);
        if (gNode) onNodeClick(gNode);
      }

      // Center on node
      if (fgRef.current) {
        if (is3D) {
          const distance = 120;
          const distRatio =
            1 + distance / Math.hypot(node.x, node.y, node.z || 0);
          fgRef.current.cameraPosition(
            {
              x: node.x * distRatio,
              y: node.y * distRatio,
              z: (node.z || 0) * distRatio,
            },
            node,
            1000,
          );
        } else {
          fgRef.current.centerAt(node.x, node.y, 500);
          fgRef.current.zoom(2.5, 500);
        }
      }
    },
    [onNodeClick, onClusterExpand, graphData, is3D],
  );

  // Click on background → deselect node
  const handleBackgroundClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  // Hover → highlight connected links (no dimming)
  const handleNodeHover = useCallback((node: any) => {
    setHoveredNodeId(node ? node.id : null);
  }, []);

  // Right-click → neighborhood exploration
  const handleNodeRightClick = useCallback(
    (node: any, event: MouseEvent) => {
      event.preventDefault();
      if (onNeighborhoodRequest && !node.isCluster) {
        // Clear selection so neighborhood nodes don't appear dimmed
        setSelectedNodeId(null);
        setHoveredNodeId(null);
        // Pause the 3D simulation before changing graph data to prevent
        // "Cannot read properties of undefined (reading 'tick')" crash.
        if (fgRef.current) {
          try { fgRef.current.pauseAnimation?.(); } catch { /* noop */ }
        }
        setBreadcrumbs((prev) => [
          ...prev,
          { label: node.label, displayName: node.name, mode: "neighborhood", nodeId: node.id },
        ]);
        onNeighborhoodRequest(node.id);
      }
    },
    [onNeighborhoodRequest],
  );

  // Navigate back to overview
  const handleBackToOverview = useCallback(() => {
    setBreadcrumbs([]);
    setSelectedNodeId(null);
    setHoveredNodeId(null);
    if (onBackToOverview) onBackToOverview();
  }, [onBackToOverview]);

  // Navigate breadcrumb
  const handleBreadcrumbClick = useCallback(
    (index: number) => {
      if (index < 0) {
        handleBackToOverview();
        return;
      }
      setSelectedNodeId(null);
      setHoveredNodeId(null);
      const crumb = breadcrumbs[index];
      setBreadcrumbs((prev) => prev.slice(0, index + 1));
      if (crumb.mode === "expand" && onClusterExpand) {
        onClusterExpand(crumb.label);
      } else if (crumb.mode === "neighborhood" && onNeighborhoodRequest && crumb.nodeId) {
        onNeighborhoodRequest(crumb.nodeId);
      } else if (crumb.mode === "overview" && onBackToOverview) {
        onBackToOverview();
      }
    },
    [breadcrumbs, onClusterExpand, onNeighborhoodRequest, onBackToOverview, handleBackToOverview],
  );

  const handleZoomIn = () => {
    if (!fgRef.current) return;
    if (is3D) {
      const pos = fgRef.current.cameraPosition();
      fgRef.current.cameraPosition(
        { x: pos.x * 0.7, y: pos.y * 0.7, z: pos.z * 0.7 },
        undefined,
        300,
      );
    } else {
      fgRef.current.zoom(fgRef.current.zoom() * 1.3, 300);
    }
  };

  const handleZoomOut = () => {
    if (!fgRef.current) return;
    if (is3D) {
      const pos = fgRef.current.cameraPosition();
      fgRef.current.cameraPosition(
        { x: pos.x * 1.4, y: pos.y * 1.4, z: pos.z * 1.4 },
        undefined,
        300,
      );
    } else {
      fgRef.current.zoom(fgRef.current.zoom() / 1.3, 300);
    }
  };

  const handleReset = () => {
    if (!fgRef.current) return;
    if (is3D) {
      fgRef.current.cameraPosition(
        { x: 0, y: 0, z: 500 },
        { x: 0, y: 0, z: 0 },
        500,
      );
    } else {
      fgRef.current.zoomToFit(400);
    }
  };

  const handleToggle3D = () => {
    fgRef.current = null;
    setSettling(true); // re-trigger settling for new renderer
    clearTimeout(settleTimerRef.current);
    settleTimerRef.current = setTimeout(() => setSettling(false), 2500);
    setIs3D((prev) => {
      if (!prev) setThreeDKey((k) => k + 1); // force fresh 3D mount
      return !prev;
    });
  };

  if (loading) {
    return (
      <Card className="flex w-full flex-col min-h-[700px]">
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent className="flex-1">
          <Skeleton className="h-full w-full rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  if (!activeData || (!graphData?.nodes.length && !scalableData?.nodes.length)) {
    return (
      <Card className="flex w-full flex-col">
        <CardHeader>
          <CardTitle className="text-sm font-medium">Graph Explorer</CardTitle>
          <CardDescription className="text-sm">
            No graph data available. Build a knowledge graph from a collection
            to visualize entities and relationships.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className={isFullscreen ? "fixed inset-4 z-50 pb-0 gap-2" : "flex w-full flex-col pb-0 gap-2 min-h-[700px]"}>
      <CardHeader className="pb-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-medium">
              Graph Explorer
            </CardTitle>
            <span className="text-muted-foreground text-xs font-normal">
              {forceData.nodes.length} nodes · {forceData.links.length} edges
              {totalNodes > forceData.nodes.length && (
                <> (total: {totalNodes.toLocaleString()} nodes · {totalEdges.toLocaleString()} edges)</>
              )}
            </span>
            {currentMode !== "full" && (
              <span className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase">
                {currentMode}
              </span>
            )}
            {!enablePointer && (
              <span className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded px-1.5 py-0.5 text-[10px] font-medium">
                perf mode
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {/* 2D / 3D toggle */}
            <Button
              variant={is3D ? "default" : "ghost"}
              size="icon"
              onClick={handleToggle3D}
              title={is3D ? "Switch to 2D" : "Switch to 3D"}
            >
              {is3D ? <Square className="h-4 w-4" /> : <Box className="h-4 w-4" />}
            </Button>
            <div className="bg-border mx-1 h-4 w-px" />
            <Button variant="ghost" size="icon" onClick={handleZoomIn}>
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleZoomOut}>
              <ZoomOut className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleReset}>
              <RotateCcw className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsFullscreen(!isFullscreen)}
            >
              {isFullscreen ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {/* Breadcrumb navigation */}
        {breadcrumbs.length > 0 && (
          <div className="flex items-center gap-1 pt-1 text-xs">
            <button
              onClick={handleBackToOverview}
              className="text-primary hover:underline flex items-center gap-0.5"
            >
              <Layers className="h-3 w-3" />
              Overview
            </button>
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-0.5">
                <ChevronRight className="text-muted-foreground h-3 w-3" />
                <button
                  onClick={() => handleBreadcrumbClick(i)}
                  className={`hover:underline ${i === breadcrumbs.length - 1 ? "text-foreground font-medium" : "text-primary"}`}
                >
                  {crumb.displayName}
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Search */}
        <div className="pt-2">
          <div className="relative max-w-sm">
            {searchLoading ? (
              <Loader2 className="text-muted-foreground absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin" />
            ) : (
              <Search className="text-muted-foreground absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2" />
            )}
            <Input
              placeholder="Search nodes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-8 text-sm"
            />
          </div>
          {serverClusterMatches && serverMatchedClusterLabels.size > 0 && (
            <p className="text-muted-foreground mt-1 text-[11px]">
              {serverMatchedClusterLabels.size} cluster matched (
              {Array.from(serverMatchedClusterLabels.entries())
                .map(([key, count]) => {
                  if (key.startsWith("subcluster__")) {
                    const parts = key.split("__");
                    const offset = parseInt(parts[2], 10);
                    const limit = parseInt(parts[3], 10);
                    const num = Math.floor(offset / limit) + 1;
                    return `${parts[1]} #${num}: ${count}`;
                  }
                  return `${key}: ${count}`;
                })
                .join(", ")}
              ) — highlighted in red
            </p>
          )}
          {searchQuery.trim() && !searchLoading && serverClusterMatches && serverMatchedClusterLabels.size === 0 && (
            <p className="text-muted-foreground mt-1 text-[11px]">
              No results found for &ldquo;{searchQuery}&rdquo;
            </p>
          )}
        </div>
      </CardHeader>

      <CardContent
        className={`relative overflow-hidden p-0 flex-1 ${isFullscreen ? "h-[calc(100vh-200px)]" : "min-h-[620px]"}`}
      >
        <div ref={containerRef} className="absolute inset-0">

        {/* ── 2D Renderer ── */}
        {!is3D && ForceGraph2D && (
          <ForceGraph2D
            ref={fgRef}
            graphData={filteredData}
            width={dimensions.width}
            height={dimensions.height}
            nodeLabel={(node: ForceGraphNode) =>
              node.isCluster
                ? `⬡ ${node.name} (${node.nodeCount} nodes)\nTop: ${(node.topEntities || []).slice(0, 3).join(", ")}`
                : `${node.name} (${node.label})`
            }
            nodeColor={(node: ForceGraphNode) => {
              if (selectedNodeId && !selectedNeighborIds.has(node.id)) return "rgba(148,163,184,0.25)";
              return node.id === selectedNodeId ? SELECTED_COLOR : (node.color || "#6b7280");
            }}
            nodeRelSize={5}
            nodeVal={(node: ForceGraphNode) => node.val || 3}
            linkLabel={(link: ForceGraphLink) =>
              link.relationshipTypes
                ? `${link.type} (${link.relationshipTypes.join(", ")})`
                : link.type
            }
            onNodeClick={handleNodeClick}
            onNodeRightClick={handleNodeRightClick}
            onBackgroundClick={handleBackgroundClick}
            onNodeHover={handleNodeHover}
            enablePointerInteraction={enablePointer}
            cooldownTicks={cooldownTicks}
            warmupTicks={warmupTicks}
            onEngineStop={handleEngineStop}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            linkCurvature={(link: any) => {
              const idx = filteredData.links.indexOf(link);
              return parallelLinkMeta.get(idx) ?? 0;
            }}
            linkDirectionalArrowLength={isDense ? 2.5 : 4}
            linkDirectionalArrowRelPos={1}
            linkWidth={(link: any) => {
              const src = typeof link.source === "object" ? link.source.id : link.source;
              const tgt = typeof link.target === "object" ? link.target.id : link.target;
              // Click-selected: thick for connected, normal for rest
              if (selectedNodeId) {
                if (src === selectedNodeId || tgt === selectedNodeId) {
                  return link.weight ? Math.min(8, Math.max(2.5, Math.sqrt(link.weight) * 1.5)) : 2.5;
                }
              }
              // Hover: slightly thicker for connected links
              if (hoveredNodeId && !selectedNodeId) {
                if (src === hoveredNodeId || tgt === hoveredNodeId) {
                  return 2;
                }
              }
              return link.weight ? Math.min(6, Math.max(1, Math.sqrt(link.weight))) : (isDense ? 0.8 : 1.5);
            }}
            linkColor={(link: any) => {
              const src = typeof link.source === "object" ? link.source.id : link.source;
              const tgt = typeof link.target === "object" ? link.target.id : link.target;
              // Click-selected: colored for connected, dimmed for rest
              if (selectedNodeId) {
                if (src === selectedNodeId || tgt === selectedNodeId) {
                  const otherNodeId = src === selectedNodeId ? tgt : src;
                  const otherNode = filteredData.nodes.find((n) => n.id === otherNodeId);
                  return otherNode?.color || "#f59e0b";
                }
                return "rgba(148,163,184,0.15)";
              }
              // Hover: colored for connected links, everything else stays normal
              if (hoveredNodeId) {
                if (src === hoveredNodeId || tgt === hoveredNodeId) {
                  const otherNodeId = src === hoveredNodeId ? tgt : src;
                  const otherNode = filteredData.nodes.find((n) => n.id === otherNodeId);
                  return otherNode?.color || "#f59e0b";
                }
              }
              return isDense ? "rgba(148,163,184,0.35)" : (link.color || "#94a3b8");
            }}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const isSelected = node.id === selectedNodeId;
              // When a node is selected, dim unrelated nodes
              const isDimmed = selectedNodeId != null && !selectedNeighborIds.has(node.id);
              const nodeColor = isDimmed
                ? "rgba(148,163,184,0.25)"
                : isSelected ? SELECTED_COLOR : (node.color || "#6b7280");
              // Does this cluster match the server search?
              let clusterMatchCount = 0;
              if (node.isCluster && serverMatchedClusterLabels) {
                // If the key is present via cluster ID (e.g. subclusters), use it; otherwise fallback to label.
                clusterMatchCount = serverMatchedClusterLabels.get(node.id) ?? serverMatchedClusterLabels.get(node.label) ?? 0;
              }
              let relMatchCount = 0;
              if (node.isCluster && selectedRelTypes && selectedRelTypes.size > 0 && node.properties?._rel_type_counts) {
                const counts = node.properties._rel_type_counts as Record<string, number>;
                for (const rt of Array.from(selectedRelTypes)) {
                  relMatchCount += (counts[rt] || 0);
                }
              }
              const isClusterMatch = clusterMatchCount > 0;
              const isRelMatch = relMatchCount > 0;
              const isHighlight = isClusterMatch || isRelMatch;
              
              // Degree-based sizing for regular nodes
              const degree = degreeMap.get(node.id) || 0;

              if (node.isCluster) {
                // ── Hexagon for cluster supernodes ──
                const size = Math.max(8, Math.min(24, Math.sqrt(node.nodeCount || 10) * 2.5));

                // Glow ring for matching clusters
                if (isHighlight) {
                  ctx.beginPath();
                  for (let i = 0; i < 6; i++) {
                    const angle = (Math.PI / 3) * i - Math.PI / 6;
                    const glowSize = size + 6;
                    const px = node.x + glowSize * Math.cos(angle);
                    const py = node.y + glowSize * Math.sin(angle);
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                  }
                  ctx.closePath();
                  ctx.fillStyle = isClusterMatch ? "rgba(239, 68, 68, 0.25)" : "rgba(59, 130, 246, 0.25)";
                  ctx.fill();
                }

                ctx.beginPath();
                for (let i = 0; i < 6; i++) {
                  const angle = (Math.PI / 3) * i - Math.PI / 6;
                  const px = node.x + size * Math.cos(angle);
                  const py = node.y + size * Math.sin(angle);
                  if (i === 0) ctx.moveTo(px, py);
                  else ctx.lineTo(px, py);
                }
                ctx.closePath();
                ctx.fillStyle = isClusterMatch ? "#dc2626" : isRelMatch ? "#2563eb" : CLUSTER_COLOR;
                ctx.fill();
                ctx.strokeStyle = isSelected ? SELECTED_COLOR : isClusterMatch ? "#ef4444" : isRelMatch ? "#3b82f6" : CLUSTER_BORDER_COLOR;
                ctx.lineWidth = isHighlight ? 3 / globalScale : 2 / globalScale;
                ctx.stroke();

                // Count badge (show match count if cluster matches)
                const countText = isClusterMatch
                  ? `${clusterMatchCount}/${node.nodeCount}`
                  : isRelMatch
                  ? `${relMatchCount}/${node.nodeCount}`
                  : `${node.nodeCount}`;
                const badgeFontSize = Math.max(8 / globalScale, 2);
                ctx.font = `bold ${badgeFontSize}px Inter, sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#fff";
                ctx.fillText(countText, node.x, node.y);

                // Label below hexagon
                if (showLabels && globalScale > LABEL_ZOOM_THRESHOLD && !isDimmed) {
                  const labelFontSize = Math.max(10 / globalScale, 1.5);
                  ctx.font = `${labelFontSize}px Inter, sans-serif`;
                  ctx.textBaseline = "top";
                  ctx.fillStyle = isClusterMatch ? "#dc2626" : isRelMatch ? "#2563eb" : "rgba(0,0,0,0.8)";
                  ctx.fillText(node.name, node.x, node.y + size + 2);
                }
              } else {
                // ── Circle for regular nodes ──
                // Degree-based sizing: hub nodes are slightly larger
                const baseRadius = isDense ? 4 : 5;
                const radius = baseRadius + Math.min(4, Math.sqrt(degree) * 0.8);

                ctx.beginPath();
                ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
                ctx.fillStyle = nodeColor;
                ctx.fill();

                if (isSelected) {
                  ctx.strokeStyle = SELECTED_COLOR;
                  ctx.lineWidth = 2 / globalScale;
                  ctx.stroke();
                }

                // Label (LoD: only when zoomed in enough)
                if (showLabels && globalScale > LABEL_ZOOM_THRESHOLD && !isDimmed) {
                  const fontSize = Math.max(10 / globalScale, 1.5);
                  ctx.font = `${fontSize}px Inter, sans-serif`;
                  ctx.textAlign = "center";
                  ctx.textBaseline = "top";
                  ctx.fillStyle = "rgba(0,0,0,0.8)";
                  ctx.fillText(node.name, node.x, node.y + radius + 2);
                }
              }
            }}
            backgroundColor="transparent"
          />
        )}

        {/* ── 3D Renderer ── */}
        {is3D && (
          <ForceGraph3DLazy
            key={`3d-${threeDKey}`}
            ref={fgRef}
            graphData={filteredData}
            width={dimensions.width}
            height={dimensions.height}
            nodeLabel={(node: ForceGraphNode) =>
              node.isCluster
                ? `⬡ ${node.name} (${node.nodeCount} nodes)`
                : `${node.name} (${node.label})`
            }
            nodeRelSize={5}
            nodeVal={(node: ForceGraphNode) => {
              const deg = degreeMap.get(node.id) || 0;
              const base = node.val || 3;
              return base + Math.min(4, Math.sqrt(deg) * 0.8);
            }}
            linkDirectionalArrowLength={isDense ? 2.5 : 4}
            linkDirectionalArrowRelPos={1}
            linkCurvature={(link: any) => {
              const idx = filteredData.links.indexOf(link);
              return parallelLinkMeta.get(idx) ?? 0;
            }}
            linkLabel={(link: ForceGraphLink) => link.type}
            linkColor={(link: any) => {
              const src = typeof link.source === "object" ? link.source.id : link.source;
              const tgt = typeof link.target === "object" ? link.target.id : link.target;
              if (selectedNodeId) {
                if (src === selectedNodeId || tgt === selectedNodeId) {
                  const otherNodeId = src === selectedNodeId ? tgt : src;
                  const otherNode = filteredData.nodes.find((n) => n.id === otherNodeId);
                  return otherNode?.color || "#f59e0b";
                }
                return "rgba(148,163,184,0.15)";
              }
              if (hoveredNodeId) {
                if (src === hoveredNodeId || tgt === hoveredNodeId) {
                  const otherNodeId = src === hoveredNodeId ? tgt : src;
                  const otherNode = filteredData.nodes.find((n) => n.id === otherNodeId);
                  return otherNode?.color || "#f59e0b";
                }
              }
              return isDense ? "rgba(148,163,184,0.35)" : (link.color || "#94a3b8");
            }}
            linkWidth={(link: any) => {
              const src = typeof link.source === "object" ? link.source.id : link.source;
              const tgt = typeof link.target === "object" ? link.target.id : link.target;
              if (selectedNodeId) {
                if (src === selectedNodeId || tgt === selectedNodeId) {
                  return link.weight ? Math.min(8, Math.max(2.5, Math.sqrt(link.weight) * 1.5)) : 2.5;
                }
              }
              if (hoveredNodeId && !selectedNodeId) {
                if (src === hoveredNodeId || tgt === hoveredNodeId) {
                  return 2;
                }
              }
              return link.weight ? Math.min(6, Math.max(1, Math.sqrt(link.weight))) : (isDense ? 0.8 : 1.5);
            }}
            nodeColor={(node: ForceGraphNode) => {
              if (selectedNodeId && !selectedNeighborIds.has(node.id)) return "rgba(148,163,184,0.25)";
              return node.id === selectedNodeId ? SELECTED_COLOR : (node.color || "#6b7280");
            }}
            onNodeClick={handleNodeClick}
            onNodeRightClick={handleNodeRightClick}
            onBackgroundClick={handleBackgroundClick}
            onNodeHover={handleNodeHover}
            enablePointerInteraction={enablePointer}
            cooldownTicks={cooldownTicks}
            warmupTicks={warmupTicks}
            onEngineStop={handleEngineStop}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            backgroundColor="rgba(0,0,0,0)"
          />
        )}

        {/* Loading placeholder while 2D graph component loads */}
        {!is3D && !ForceGraph2D && (
          <div className="flex h-full min-h-[300px] items-center justify-center">
            <Skeleton className="h-[300px] w-full rounded-lg" />
          </div>
        )}

        {/* Settling overlay — covers graph while force simulation stabilizes */}
        <div
          className={`absolute inset-0 z-10 flex items-center justify-center bg-background/80 backdrop-blur-sm transition-opacity duration-500 ${
            settling ? "opacity-100" : "opacity-0 pointer-events-none"
          }`}
        >
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Settling layout…</span>
          </div>
        </div>

        {/* Interaction hints */}
        <div className="absolute bottom-2 left-2 text-[10px] text-muted-foreground opacity-60 pointer-events-none select-none">
          {currentMode === "overview" && "Click cluster to expand · Right-click node for neighborhood"}
          {currentMode === "expand" && "Viewing cluster contents · Right-click for neighborhood"}
          {currentMode === "neighborhood" && "Ego-graph view · Click nodes to explore"}
          {currentMode === "full" && forceData.nodes.length > 200 && "Large graph — zoom to see labels · Right-click for neighborhood"}
        </div>
        </div>
      </CardContent>
    </Card>
  );
}
