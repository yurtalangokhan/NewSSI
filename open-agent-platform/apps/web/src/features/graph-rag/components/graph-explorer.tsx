/**
 * Interactive force-directed graph visualization.
 * Supports 2D (react-force-graph-2d) and 3D (react-force-graph-3d) modes
 * with a toggle button to switch between them.
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
  Maximize2,
  Minimize2,
  Search,
  Square,
  ZoomIn,
  ZoomOut,
  RotateCcw,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { GraphData, GraphNode } from "@/types/graph";
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

interface GraphExplorerProps {
  graphData: GraphData | null;
  loading?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  /** Filter graph to only show nodes with these labels */
  selectedLabels?: Set<string>;
  /** Filter graph to only show edges with these relationship types */
  selectedRelTypes?: Set<string>;
}

export function GraphExplorer({
  graphData,
  loading,
  onNodeClick,
  selectedLabels,
  selectedRelTypes,
}: GraphExplorerProps) {
  const fgRef = useRef<any>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const [ForceGraph2D, setForceGraph2D] = useState<any>(null);
  const [is3D, setIs3D] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

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

  // Convert GraphData → ForceGraphData (with label/relType filters)
  const forceData: ForceGraphData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] };

    const hasLabelFilter = selectedLabels && selectedLabels.size > 0;
    const hasRelFilter = selectedRelTypes && selectedRelTypes.size > 0;

    const filteredNodes = hasLabelFilter
      ? graphData.nodes.filter((n) => selectedLabels.has(n.label))
      : graphData.nodes;

    const nodes: ForceGraphNode[] = filteredNodes.map((n) => ({
      id: n.id,
      name: n.name,
      label: n.label,
      val: 3,
      color: getLabelColor(n.label),
      properties: n.properties,
    }));

    const nodeIds = new Set(nodes.map((n) => n.id));
    const filteredEdges = graphData.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .filter((e) => !hasRelFilter || selectedRelTypes.has(e.type));

    const links: ForceGraphLink[] = filteredEdges.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type,
      color: "#94a3b8",
    }));

    return { nodes, links };
  }, [graphData, selectedLabels, selectedRelTypes]);

  // Filter by search
  const filteredData: ForceGraphData = useMemo(() => {
    if (!searchQuery.trim()) return forceData;
    const q = searchQuery.toLowerCase();
    const matchedNodes = forceData.nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.label.toLowerCase().includes(q),
    );
    const matchedIds = new Set(matchedNodes.map((n) => n.id));
    // Also include connected nodes
    const connectedLinks = forceData.links.filter(
      (l) => {
        const src = typeof l.source === 'object' ? (l.source as any).id : l.source;
        const tgt = typeof l.target === 'object' ? (l.target as any).id : l.target;
        return matchedIds.has(src) || matchedIds.has(tgt);
      }
    );
    const connectedNodeIds = new Set<string>();
    connectedLinks.forEach((l) => {
      const src = typeof l.source === 'object' ? (l.source as any).id : l.source;
      const tgt = typeof l.target === 'object' ? (l.target as any).id : l.target;
      connectedNodeIds.add(src);
      connectedNodeIds.add(tgt);
    });
    const allRelevantNodes = forceData.nodes.filter(
      (n) => matchedIds.has(n.id) || connectedNodeIds.has(n.id),
    );
    return { nodes: allRelevantNodes, links: connectedLinks };
  }, [forceData, searchQuery]);

  const handleNodeClick = useCallback(
    (node: any) => {
      setSelectedNodeId(node.id);
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
    [onNodeClick, graphData, is3D],
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

  if (!graphData || graphData.nodes.length === 0) {
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
          <CardTitle className="text-sm font-medium">
            Graph Explorer
            <span className="text-muted-foreground ml-2 text-xs font-normal">
              {forceData.nodes.length} nodes · {forceData.links.length} edges
            </span>
          </CardTitle>
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

        {/* Search */}
        <div className="pt-2">
          <div className="relative max-w-sm">
            <Search className="text-muted-foreground absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2" />
            <Input
              placeholder="Search nodes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-8 text-sm"
            />
          </div>
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
              `${node.name} (${node.label})`
            }
            nodeColor={(node: ForceGraphNode) =>
              node.id === selectedNodeId ? "#f59e0b" : (node.color || "#6b7280")
            }
            nodeRelSize={5}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkLabel={(link: ForceGraphLink) => link.type}
            linkColor={(link: ForceGraphLink) => link.color || "#94a3b8"}
            linkWidth={1.5}
            onNodeClick={handleNodeClick}
            cooldownTicks={100}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const label = node.name;
              const fontSize = Math.max(10 / globalScale, 1.5);
              ctx.font = `${fontSize}px Inter, sans-serif`;
              const nodeColor = node.id === selectedNodeId ? "#f59e0b" : (node.color || "#6b7280");

              // Draw node circle
              ctx.beginPath();
              ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI);
              ctx.fillStyle = nodeColor;
              ctx.fill();

              // Draw border for selected
              if (node.id === selectedNodeId) {
                ctx.strokeStyle = "#f59e0b";
                ctx.lineWidth = 2 / globalScale;
                ctx.stroke();
              }

              // Draw label
              if (globalScale > 0.7) {
                ctx.textAlign = "center";
                ctx.textBaseline = "top";
                ctx.fillStyle = "rgba(0,0,0,0.8)";
                ctx.fillText(label, node.x, node.y + 7);
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
              `${node.name} (${node.label})`
            }
            nodeColor={(node: ForceGraphNode) =>
              node.id === selectedNodeId ? "#f59e0b" : (node.color || "#6b7280")
            }
            nodeRelSize={5}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkLabel={(link: ForceGraphLink) => link.type}
            linkColor={(link: ForceGraphLink) => link.color || "#94a3b8"}
            linkWidth={1.5}
            onNodeClick={handleNodeClick}
            cooldownTicks={100}
            backgroundColor="rgba(0,0,0,0)"
          />
        )}

        {/* Loading placeholder while 2D graph component loads */}
        {!is3D && !ForceGraph2D && (
          <div className="flex h-full min-h-[300px] items-center justify-center">
            <Skeleton className="h-[300px] w-full rounded-lg" />
          </div>
        )}
        </div>
      </CardContent>
    </Card>
  );
}
