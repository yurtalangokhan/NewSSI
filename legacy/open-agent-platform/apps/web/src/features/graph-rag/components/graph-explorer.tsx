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
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);

  // Server-side cluster search results: label → match count
  const [serverClusterMatches, setServerClusterMatches] = useState<Record<string, number> | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Matched cluster labels from server search
  const serverMatchedClusterLabels = useMemo(() => {
    if (!serverClusterMatches) return new Map<string, number>();
    return new Map(Object.entries(serverClusterMatches));
  }, [serverClusterMatches]);

  // Determine which data source to use
  const activeData = scalableData || graphData;
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

    const filteredNodes = hasLabelFilter
      ? rawNodes.filter((n) => selectedLabels.has(n.label))
      : rawNodes;

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

    const nodeIds = new Set(nodes.map((n) => n.id));
    const filteredEdges = rawEdges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .filter((e) => !hasRelFilter || selectedRelTypes.has(e.type));

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
        (n.isCluster && serverMatchedClusterLabels.has(n.label)),
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

  // ── Adaptive performance settings ──
  const nodeCount = filteredData.nodes.length;
  const enablePointer = nodeCount < POINTER_DISABLE_THRESHOLD;
  const cooldownTicks = nodeCount > FAST_COOLDOWN_THRESHOLD ? 50 : 100;
  const warmupTicks = nodeCount > FAST_COOLDOWN_THRESHOLD ? 30 : 0;
  const showLabels = nodeCount < HIDE_LABELS_THRESHOLD;

  const handleNodeClick = useCallback(
    (node: any) => {
      setSelectedNodeId(node.id);

      // Cluster supernode → drill down
      if (node.isCluster && onClusterExpand) {
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

  // Right-click → neighborhood exploration
  const handleNodeRightClick = useCallback(
    (node: any, event: MouseEvent) => {
      event.preventDefault();
      if (onNeighborhoodRequest && !node.isCluster) {
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
    if (onBackToOverview) onBackToOverview();
  }, [onBackToOverview]);

  // Navigate breadcrumb
  const handleBreadcrumbClick = useCallback(
    (index: number) => {
      if (index < 0) {
        handleBackToOverview();
        return;
      }
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
    setIs3D((prev) => !prev);
  };

  if (loading) {
    return (
      <Card className="flex w-full flex-col min-h-[560px]">
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
    <Card className={isFullscreen ? "fixed inset-4 z-50 pb-0 gap-2" : "flex w-full flex-col pb-0 gap-2 min-h-[560px]"}>
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
                .map(([label, count]) => `${label}: ${count}`)
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
        className={`relative overflow-hidden p-0 flex-1 ${isFullscreen ? "h-[calc(100vh-200px)]" : "min-h-[480px]"}`}
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
            nodeColor={(node: ForceGraphNode) =>
              node.id === selectedNodeId ? SELECTED_COLOR : (node.color || "#6b7280")
            }
            nodeRelSize={5}
            nodeVal={(node: ForceGraphNode) => node.val || 3}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkLabel={(link: ForceGraphLink) =>
              link.relationshipTypes
                ? `${link.type} (${link.relationshipTypes.join(", ")})`
                : link.type
            }
            linkColor={(link: ForceGraphLink) => link.color || "#94a3b8"}
            linkWidth={(link: ForceGraphLink) =>
              link.weight ? Math.min(6, Math.max(1, Math.sqrt(link.weight))) : 1.5
            }
            onNodeClick={handleNodeClick}
            onNodeRightClick={handleNodeRightClick}
            enablePointerInteraction={enablePointer}
            cooldownTicks={cooldownTicks}
            warmupTicks={warmupTicks}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const isSelected = node.id === selectedNodeId;
              const nodeColor = isSelected ? SELECTED_COLOR : (node.color || "#6b7280");
              // Does this cluster match the server search?
              const clusterMatchCount = node.isCluster
                ? serverMatchedClusterLabels.get(node.label) ?? 0
                : 0;
              const isClusterMatch = clusterMatchCount > 0;

              if (node.isCluster) {
                // ── Hexagon for cluster supernodes ──
                const size = Math.max(8, Math.min(24, Math.sqrt(node.nodeCount || 10) * 2.5));

                // Glow ring for matching clusters
                if (isClusterMatch) {
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
                  ctx.fillStyle = "rgba(239, 68, 68, 0.25)";
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
                ctx.fillStyle = isClusterMatch ? "#dc2626" : CLUSTER_COLOR;
                ctx.fill();
                ctx.strokeStyle = isSelected ? SELECTED_COLOR : isClusterMatch ? "#ef4444" : CLUSTER_BORDER_COLOR;
                ctx.lineWidth = isClusterMatch ? 3 / globalScale : 2 / globalScale;
                ctx.stroke();

                // Count badge (show match count if cluster matches)
                const countText = isClusterMatch
                  ? `${clusterMatchCount}/${node.nodeCount}`
                  : `${node.nodeCount}`;
                const badgeFontSize = Math.max(8 / globalScale, 2);
                ctx.font = `bold ${badgeFontSize}px Inter, sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#fff";
                ctx.fillText(countText, node.x, node.y);

                // Label below hexagon
                if (showLabels && globalScale > LABEL_ZOOM_THRESHOLD) {
                  const labelFontSize = Math.max(10 / globalScale, 1.5);
                  ctx.font = `${labelFontSize}px Inter, sans-serif`;
                  ctx.textBaseline = "top";
                  ctx.fillStyle = isClusterMatch ? "#dc2626" : "rgba(0,0,0,0.8)";
                  ctx.fillText(node.name, node.x, node.y + size + 2);
                }
              } else {
                // ── Circle for regular nodes ──
                const radius = 5;

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
                if (showLabels && globalScale > LABEL_ZOOM_THRESHOLD) {
                  const fontSize = Math.max(10 / globalScale, 1.5);
                  ctx.font = `${fontSize}px Inter, sans-serif`;
                  ctx.textAlign = "center";
                  ctx.textBaseline = "top";
                  ctx.fillStyle = "rgba(0,0,0,0.8)";
                  ctx.fillText(node.name, node.x, node.y + 7);
                }
              }
            }}
            backgroundColor="transparent"
          />
        )}

        {/* ── 3D Renderer ── */}
        {is3D && (
          <ForceGraph3DLazy
            ref={fgRef}
            graphData={filteredData}
            width={dimensions.width}
            height={dimensions.height}
            nodeLabel={(node: ForceGraphNode) =>
              node.isCluster
                ? `⬡ ${node.name} (${node.nodeCount} nodes)`
                : `${node.name} (${node.label})`
            }
            nodeColor={(node: ForceGraphNode) =>
              node.id === selectedNodeId ? SELECTED_COLOR : (node.color || "#6b7280")
            }
            nodeRelSize={5}
            nodeVal={(node: ForceGraphNode) => node.val || 3}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkLabel={(link: ForceGraphLink) => link.type}
            linkColor={(link: ForceGraphLink) => link.color || "#94a3b8"}
            linkWidth={(link: ForceGraphLink) =>
              link.weight ? Math.min(6, Math.max(1, Math.sqrt(link.weight))) : 1.5
            }
            onNodeClick={handleNodeClick}
            onNodeRightClick={handleNodeRightClick}
            enablePointerInteraction={enablePointer}
            cooldownTicks={cooldownTicks}
            warmupTicks={warmupTicks}
            backgroundColor="rgba(0,0,0,0)"
          />
        )}

        {/* Loading placeholder while 2D graph component loads */}
        {!is3D && !ForceGraph2D && (
          <div className="flex h-full min-h-[300px] items-center justify-center">
            <Skeleton className="h-[300px] w-full rounded-lg" />
          </div>
        )}

        {/* Interaction hints */}
        <div className="absolute bottom-2 left-2 text-[10px] text-muted-foreground opacity-60 pointer-events-none select-none">
          {currentMode === "overview" && "Click cluster to expand · Right-click node for neighborhood"}
          {currentMode === "expand" && "Viewing cluster contents · Right-click node for neighborhood"}
          {currentMode === "neighborhood" && "Ego-graph view · Click nodes to explore"}
          {currentMode === "full" && forceData.nodes.length > 200 && "Large graph — zoom to see labels"}
        </div>
        </div>
      </CardContent>
    </Card>
  );
}
