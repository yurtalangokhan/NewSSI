/**
 * Interactive force-directed knowledge graph visualization.
 * Supports 2D (react-force-graph-2d) and 3D (react-force-graph-3d) modes,
 * cluster supernodes with click-to-expand, level-of-detail labels,
 * neighborhood ego-graphs, and breadcrumb navigation.
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { forceCollide as d3ForceCollide } from "d3-force-3d";
import dynamic from "next/dynamic";
import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import {
  SvgZoomIn,
  SvgZoomOut,
  SvgMaximize2,
  SvgFold,
  SvgExpand,
  SvgRefreshCw,
  SvgChevronRight,
} from "@opal/icons";
import { cn } from "@/lib/utils";
import { ThreeDotsLoader } from "@/components/Loading";
import {
  isClusterNode,
  isClusterEdge,
  searchGraphEntityClusters,
  type GraphNode,
  type ClusteredGraphData,
  type GraphData,
  type ScalableNode,
  type ScalableEdge,
  type ForceGraphNode,
  type ForceGraphLink,
  type ForceGraphData,
} from "@/lib/langconnect";

// Lazy-load 3D renderer — Three.js uses WebGL constants at import time which
// crashes in Node/SSR. next/dynamic with ssr:false ensures browser-only eval.
const ForceGraph3DLazy = dynamic(
  () => import("./ForceGraph3DWrapper"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <ThreeDotsLoader />
      </div>
    ),
  }
);

// ── Color palette ──────────────────────────────────────────────────────────
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

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

function getLabelColor(label: string): string {
  return LABEL_COLORS[label] || `hsl(${hashString(label) % 360}, 60%, 50%)`;
}

function getNodeColorExpanded(name: string, label: string): string {
  const baseHue = hashString(label) % 360;
  const offset = hashString(name) % 60;
  const hue = (baseHue + offset) % 360;
  const lightness = 40 + (hashString(name + "L") % 20);
  return `hsl(${hue}, 55%, ${lightness}%)`;
}

const CLUSTER_COLOR = "#d97706";
const CLUSTER_BORDER_COLOR = "#f59e0b";
const SELECTED_COLOR = "#f59e0b";

// ── Performance thresholds ─────────────────────────────────────────────────
const POINTER_DISABLE_THRESHOLD = 2000;
const FAST_COOLDOWN_THRESHOLD = 1000;
const HIDE_LABELS_THRESHOLD = 3000;
const LABEL_ZOOM_THRESHOLD = 0.7;

interface BreadcrumbItem {
  label: string;
  displayName: string;
  mode: "overview" | "expand" | "neighborhood" | "full";
  nodeId?: string;
}

interface GraphExplorerProps {
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
  /** True when this tab is the active/visible one — triggers canvas re-measurement */
  isActive?: boolean;
}

export default function GraphExplorer({
  scalableData,
  graphData,
  loading,
  collectionId,
  onNodeClick,
  onClusterExpand,
  onNeighborhoodRequest,
  onBackToOverview,
  selectedLabels,
  selectedRelTypes,
  isActive,
}: GraphExplorerProps) {
  const fgRef = useRef<any>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const containerNodeRef = useRef<HTMLDivElement | null>(null);
  const [ForceGraph2D, setForceGraph2D] = useState<any>(null);
  const [is3D, setIs3D] = useState(false);
  const [threeDKey, setThreeDKey] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 800, height: 700 });
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);

  // Settling overlay while force simulation stabilizes
  const [settling, setSettling] = useState(true);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prevDataFingerprintRef = useRef("");

  // Server-side cluster search
  const [serverClusterMatches, setServerClusterMatches] = useState<Record<string, number> | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const serverMatchedClusterLabels = useMemo(() => {
    if (!serverClusterMatches) return new Map<string, number>();
    return new Map(Object.entries(serverClusterMatches));
  }, [serverClusterMatches]);

  const currentMode = scalableData?.mode ?? "full";
  const totalNodes = scalableData?.total_node_count ?? graphData?.nodes.length ?? 0;
  const totalEdges = scalableData?.total_edge_count ?? graphData?.edges.length ?? 0;

  // Dynamic import of react-force-graph-2d
  useEffect(() => {
    import("react-force-graph-2d").then((mod) => {
      setForceGraph2D(() => mod.default);
    });
  }, []);

  // ResizeObserver — callback ref fires every DOM mount/unmount
  const containerRef = useCallback((node: HTMLDivElement | null) => {
    observerRef.current?.disconnect();
    observerRef.current = null;
    containerNodeRef.current = node;
    if (!node) return;
    const w = node.clientWidth;
    const h = node.clientHeight;
    if (w > 0 && h > 0) setDimensions({ width: w, height: h });
    const ro = new ResizeObserver(() => {
      const rw = node.clientWidth;
      const rh = node.clientHeight;
      if (rw > 0 && rh > 0) {
        setDimensions((prev) =>
          prev.width === rw && prev.height === rh ? prev : { width: rw, height: rh }
        );
      }
    });
    ro.observe(node);
    observerRef.current = ro;
  }, []);

  // Re-measure after every scalableData change — the ResizeObserver only fires
  // on size changes, but the container may already be at the correct size when
  // new data arrives (e.g. back-to-overview), leaving dimensions stale.
  useEffect(() => {
    const node = containerNodeRef.current;
    if (!node) return;
    const measure = () => {
      const rw = node.clientWidth;
      const rh = node.clientHeight;
      if (rw > 0 && rh > 0) {
        setDimensions((prev) =>
          prev.width === rw && prev.height === rh ? prev : { width: rw, height: rh }
        );
      }
    };
    // Measure immediately after layout, then again after any CSS transitions finish
    const raf = requestAnimationFrame(measure);
    const timer = setTimeout(measure, 550);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    };
  }, [scalableData]);

  // Re-measure when this tab becomes visible (after the max-width CSS transition)
  useEffect(() => {
    if (!isActive) return;
    const node = containerNodeRef.current;
    if (!node) return;
    const measure = () => {
      const rw = node.clientWidth;
      const rh = node.clientHeight;
      if (rw > 0 && rh > 0) {
        setDimensions((prev) =>
          prev.width === rw && prev.height === rh ? prev : { width: rw, height: rh }
        );
      }
    };
    // Immediate + after transition (500ms) + small buffer
    const raf = requestAnimationFrame(measure);
    const t1 = setTimeout(measure, 100);
    const t2 = setTimeout(measure, 550);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [isActive]);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  // Convert ClusteredGraphData → ForceGraphData (with filtering)
  const forceData: ForceGraphData = useMemo(() => {
    const activeData = scalableData;
    if (!activeData) return { nodes: [], links: [] };

    const rawNodes: ScalableNode[] = activeData.nodes;
    const rawEdges: ScalableEdge[] = activeData.edges;

    const hasLabelFilter = (selectedLabels?.size ?? 0) > 0;
    const hasRelFilter = (selectedRelTypes?.size ?? 0) > 0;

    let filteredNodes: ScalableNode[];
    let filteredEdges: ScalableEdge[];

    if (hasLabelFilter && hasRelFilter) {
      const labelSet = selectedLabels!;
      const relSet = selectedRelTypes!;
      const nodeMap = new Map(rawNodes.map((n) => [n.id, n]));
      filteredEdges = rawEdges.filter((e) => {
        const typeMatches = isClusterEdge(e)
          ? e.relationship_types.some((rt) => relSet.has(rt))
          : relSet.has(e.type);
        if (!typeMatches) return false;
        const src = nodeMap.get(e.source);
        const tgt = nodeMap.get(e.target);
        return (src && labelSet.has(src.label)) || (tgt && labelSet.has(tgt.label));
      });
      const connectedIds = new Set(filteredEdges.flatMap((e) => [e.source, e.target]));
      filteredNodes = rawNodes.filter((n) => connectedIds.has(n.id));
    } else if (hasRelFilter) {
      filteredEdges = rawEdges.filter((e) =>
        isClusterEdge(e)
          ? e.relationship_types.some((rt) => selectedRelTypes!.has(rt))
          : selectedRelTypes!.has(e.type)
      );
      const connectedIds = new Set(filteredEdges.flatMap((e) => [e.source, e.target]));
      filteredNodes = rawNodes.filter((n) => connectedIds.has(n.id));
    } else if (hasLabelFilter) {
      filteredNodes = rawNodes.filter((n) => selectedLabels!.has(n.label));
      const nodeIds = new Set(filteredNodes.map((n) => n.id));
      filteredEdges = rawEdges.filter(
        (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
      );
    } else {
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
      const useNameColor =
        currentMode === "expand" || currentMode === "neighborhood";
      return {
        id: n.id,
        name: n.name,
        label: n.label,
        val: 3,
        color: useNameColor
          ? getNodeColorExpanded(n.name, n.label)
          : getLabelColor(n.label),
        properties: (n as any).properties,
      };
    });

    const links: ForceGraphLink[] = filteredEdges.map((e) =>
      isClusterEdge(e)
        ? {
            source: e.source,
            target: e.target,
            type: e.type,
            color: "#94a3b8",
            weight: e.weight,
            relationshipTypes: e.relationship_types,
          }
        : { source: e.source, target: e.target, type: e.type, color: "#94a3b8" }
    );

    return { nodes, links };
  }, [scalableData, selectedLabels, selectedRelTypes, currentMode]);

  // Settling overlay trigger
  useEffect(() => {
    const fp = `${scalableData?.mode}-${forceData.nodes.length}-${scalableData?.scope_label}`;
    if (fp !== prevDataFingerprintRef.current && forceData.nodes.length > 0) {
      prevDataFingerprintRef.current = fp;
      setSettling(true);
      clearTimeout(settleTimerRef.current);
      settleTimerRef.current = setTimeout(() => setSettling(false), 2500);
    }
    return () => clearTimeout(settleTimerRef.current);
  }, [forceData, scalableData?.mode, scalableData?.scope_label]);

  const handleEngineStop = useCallback(() => {
    clearTimeout(settleTimerRef.current);
    setSettling(false);
  }, []);

  // Degree map
  const degreeMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const l of forceData.links) {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      map.set(src, (map.get(src) || 0) + 1);
      map.set(tgt, (map.get(tgt) || 0) + 1);
    }
    return map;
  }, [forceData]);

  // Parallel link curvature
  const parallelLinkMeta = useMemo(() => {
    const pairCount = new Map<string, number>();
    const pairIndex = new Map<string, number>();
    for (const l of forceData.links) {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      const key = src < tgt ? `${src}||${tgt}` : `${tgt}||${src}`;
      pairCount.set(key, (pairCount.get(key) || 0) + 1);
    }
    const curvatures = new Map<number, number>();
    forceData.links.forEach((l, idx) => {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      const key = src < tgt ? `${src}||${tgt}` : `${tgt}||${src}`;
      const count = pairCount.get(key) || 1;
      if (count <= 1) {
        curvatures.set(idx, 0);
      } else {
        const i = pairIndex.get(key) || 0;
        pairIndex.set(key, i + 1);
        const sign = i % 2 === 0 ? 1 : -1;
        const magnitude = 0.04 + Math.floor(i / 2) * 0.04;
        curvatures.set(idx, sign * magnitude);
      }
    });
    return curvatures;
  }, [forceData]);

  // Neighbours of selected node
  const selectedNeighborIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const ids = new Set<string>([selectedNodeId]);
    for (const l of forceData.links) {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      if (src === selectedNodeId) ids.add(tgt);
      if (tgt === selectedNodeId) ids.add(src);
    }
    return ids;
  }, [selectedNodeId, forceData]);

  // Search filter
  const filteredData: ForceGraphData = useMemo(() => {
    if (!searchQuery.trim()) return forceData;
    const q = searchQuery.toLowerCase();
    const matchedNodes = forceData.nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.label.toLowerCase().includes(q) ||
        n.topEntities?.some((e) => e.toLowerCase().includes(q)) ||
        (n.isCluster &&
          (serverMatchedClusterLabels.has(n.label) ||
            serverMatchedClusterLabels.has(n.id)))
    );
    const matchedIds = new Set(matchedNodes.map((n) => n.id));
    const connectedLinks = forceData.links.filter((l) => {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      return matchedIds.has(src) || matchedIds.has(tgt);
    });
    const connectedNodeIds = new Set<string>();
    connectedLinks.forEach((l) => {
      connectedNodeIds.add(
        typeof l.source === "object" ? (l.source as any).id : (l.source as string)
      );
      connectedNodeIds.add(
        typeof l.target === "object" ? (l.target as any).id : (l.target as string)
      );
    });
    return {
      nodes: forceData.nodes.filter(
        (n) => matchedIds.has(n.id) || connectedNodeIds.has(n.id)
      ),
      links: connectedLinks,
    };
  }, [forceData, searchQuery, serverMatchedClusterLabels]);

  // Performance
  const nodeCount = filteredData.nodes.length;
  const linkCount = filteredData.links.length;
  const enablePointer = nodeCount < POINTER_DISABLE_THRESHOLD;
  const cooldownTicks = nodeCount > FAST_COOLDOWN_THRESHOLD ? 50 : 100;
  const warmupTicks = nodeCount > FAST_COOLDOWN_THRESHOLD ? 80 : 120;
  const showLabels = nodeCount < HIDE_LABELS_THRESHOLD;
  const isDense = linkCount > nodeCount * 3;

  // D3 force configuration
  useEffect(() => {
    const apply = () => {
      if (!fgRef.current) return;
      const fg = fgRef.current;
      const chargeStrength = is3D
        ? isDense ? -500 : -350
        : isDense ? -300 : -180;
      fg.d3Force("charge")?.strength(chargeStrength).distanceMax(is3D ? 800 : 500);
      fg.d3Force("link")?.distance(is3D ? (isDense ? 140 : 100) : isDense ? 80 : 55);
      const collide = d3ForceCollide()
        .radius((node: any) => {
          if (node.__linkMid) return (node.__linkMidR || 4) + (is3D ? 4 : 0);
          if (node.isCluster) {
            const size = Math.max(8, Math.min(24, Math.sqrt(node.nodeCount || 10) * 2.5));
            return size + 10 + (is3D ? 8 : 0);
          }
          const deg = degreeMap.get(node.id) || 0;
          const r = (isDense ? 4 : 5) + Math.min(4, Math.sqrt(deg) * 0.8);
          return r + 12 + (is3D ? 8 : 0);
        })
        .strength(1.0)
        .iterations(5);
      fg.d3Force("collide", collide);
      fg.d3Force("center")?.strength(1);
      fg.d3Force("radial", null);
      fg.d3ReheatSimulation?.();
    };
    apply();
    const t = setTimeout(apply, 200);
    return () => clearTimeout(t);
  }, [isDense, filteredData, degreeMap, is3D]);

  // Debounced server-side cluster search
  const hasClusterNodes = useMemo(
    () => forceData.nodes.some((n) => n.isCluster),
    [forceData]
  );
  useEffect(() => {
    clearTimeout(searchDebounce.current);
    if (!searchQuery.trim() || !hasClusterNodes || !collectionId) {
      setServerClusterMatches(null);
      setSearchLoading(false);
      return;
    }
    setSearchLoading(true);
    searchDebounce.current = setTimeout(async () => {
      try {
        const results = await searchGraphEntityClusters(collectionId, searchQuery);
        setServerClusterMatches(results);
      } catch {
        setServerClusterMatches(null);
      }
      setSearchLoading(false);
    }, 400);
    return () => clearTimeout(searchDebounce.current);
  }, [searchQuery, hasClusterNodes, collectionId]);

  // ── Interaction handlers ───────────────────────────────────────────────────
  const handleNodeClick = useCallback(
    (node: any) => {
      setSelectedNodeId(node.id);
      if (node.isCluster && onClusterExpand) {
        setSelectedNodeId(null);
        setHoveredNodeId(null);
        try { fgRef.current?.pauseAnimation?.(); } catch { /* noop */ }
        const expandId =
          typeof node.id === "string" && node.id.startsWith("subcluster__")
            ? node.id
            : node.label;
        setBreadcrumbs((prev) => [
          ...prev,
          { label: expandId, displayName: node.name, mode: "expand" },
        ]);
        onClusterExpand(expandId);
        return;
      }
      if (onNodeClick) {
        // Look up in flat graphData first; fall back to scalableData for
        // expand / neighborhood views where nodes may not be in graphData.
        let gNode = graphData?.nodes.find((n) => n.id === node.id);
        if (!gNode && scalableData) {
          const sNode = scalableData.nodes.find((n) => n.id === node.id);
          if (sNode && !isClusterNode(sNode)) gNode = sNode as GraphNode;
        }
        if (gNode) onNodeClick(gNode);
      }
      if (fgRef.current) {
        if (is3D) {
          const d = 120;
          const r = 1 + d / Math.hypot(node.x, node.y, node.z || 0);
          fgRef.current.cameraPosition(
            { x: node.x * r, y: node.y * r, z: (node.z || 0) * r },
            node,
            1000
          );
        } else {
          fgRef.current.centerAt(node.x, node.y, 500);
          fgRef.current.zoom(2.5, 500);
        }
      }
    },
    [onNodeClick, onClusterExpand, graphData, scalableData, is3D]
  );

  const handleBackgroundClick = useCallback(() => setSelectedNodeId(null), []);
  const handleNodeHover = useCallback(
    (node: any) => setHoveredNodeId(node?.id ?? null),
    []
  );

  const handleNodeRightClick = useCallback(
    (node: any, event: MouseEvent) => {
      event.preventDefault();
      if (onNeighborhoodRequest && !node.isCluster) {
        setSelectedNodeId(null);
        setHoveredNodeId(null);
        try { fgRef.current?.pauseAnimation?.(); } catch { /* noop */ }
        setBreadcrumbs((prev) => [
          ...prev,
          {
            label: node.label,
            displayName: node.name,
            mode: "neighborhood",
            nodeId: node.id,
          },
        ]);
        onNeighborhoodRequest(node.id);
      }
    },
    [onNeighborhoodRequest]
  );

  const handleBackToOverview = useCallback(() => {
    setBreadcrumbs([]);
    setSelectedNodeId(null);
    setHoveredNodeId(null);
    onBackToOverview?.();
  }, [onBackToOverview]);

  const handleBreadcrumbClick = useCallback(
    (index: number) => {
      if (index < 0) { handleBackToOverview(); return; }
      setSelectedNodeId(null);
      setHoveredNodeId(null);
      const crumb = breadcrumbs[index];
      if (!crumb) return;
      setBreadcrumbs((prev) => prev.slice(0, index + 1));
      if (crumb.mode === "expand") onClusterExpand?.(crumb.label);
      else if (crumb.mode === "neighborhood" && crumb.nodeId) onNeighborhoodRequest?.(crumb.nodeId);
      else if (crumb.mode === "overview") handleBackToOverview();
    },
    [breadcrumbs, onClusterExpand, onNeighborhoodRequest, handleBackToOverview]
  );

  // Zoom / view controls
  const handleZoomIn = () => {
    if (!fgRef.current) return;
    if (is3D) {
      const p = fgRef.current.cameraPosition();
      fgRef.current.cameraPosition({ x: p.x * 0.7, y: p.y * 0.7, z: p.z * 0.7 }, undefined, 300);
    } else {
      fgRef.current.zoom(fgRef.current.zoom() * 1.3, 300);
    }
  };
  const handleZoomOut = () => {
    if (!fgRef.current) return;
    if (is3D) {
      const p = fgRef.current.cameraPosition();
      fgRef.current.cameraPosition({ x: p.x * 1.4, y: p.y * 1.4, z: p.z * 1.4 }, undefined, 300);
    } else {
      fgRef.current.zoom(fgRef.current.zoom() / 1.3, 300);
    }
  };
  const handleReset = () => {
    if (!fgRef.current) return;
    if (is3D) {
      fgRef.current.cameraPosition({ x: 0, y: 0, z: 500 }, { x: 0, y: 0, z: 0 }, 500);
    } else {
      fgRef.current.zoomToFit(400);
    }
  };
  const handleToggle3D = () => {
    fgRef.current = null;
    setSettling(true);
    clearTimeout(settleTimerRef.current);
    settleTimerRef.current = setTimeout(() => setSettling(false), 2500);
    setIs3D((prev) => {
      if (!prev) setThreeDKey((k) => k + 1);
      return !prev;
    });
  };

  // ── Link props helpers (shared by 2D + 3D) ────────────────────────────────
  const getLinkColor = (link: any) => {
    const src = typeof link.source === "object" ? link.source.id : link.source;
    const tgt = typeof link.target === "object" ? link.target.id : link.target;
    if (selectedNodeId) {
      if (src === selectedNodeId || tgt === selectedNodeId) {
        const otherId = src === selectedNodeId ? tgt : src;
        const other = filteredData.nodes.find((n) => n.id === otherId);
        return other?.color || "#f59e0b";
      }
      return "rgba(148,163,184,0.15)";
    }
    if (hoveredNodeId) {
      if (src === hoveredNodeId || tgt === hoveredNodeId) {
        const otherId = src === hoveredNodeId ? tgt : src;
        const other = filteredData.nodes.find((n) => n.id === otherId);
        return other?.color || "#f59e0b";
      }
    }
    return isDense ? "rgba(148,163,184,0.35)" : link.color || "#94a3b8";
  };

  const getLinkWidth = (link: any) => {
    const src = typeof link.source === "object" ? link.source.id : link.source;
    const tgt = typeof link.target === "object" ? link.target.id : link.target;
    if (selectedNodeId && (src === selectedNodeId || tgt === selectedNodeId)) {
      return link.weight ? Math.min(8, Math.max(2.5, Math.sqrt(link.weight) * 1.5)) : 2.5;
    }
    if (hoveredNodeId && !selectedNodeId && (src === hoveredNodeId || tgt === hoveredNodeId)) {
      return 2;
    }
    return link.weight
      ? Math.min(6, Math.max(1, Math.sqrt(link.weight)))
      : isDense ? 0.8 : 1.5;
  };

  // Canvas node object (2D only)
  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isSelected = node.id === selectedNodeId;
      const isDimmed = selectedNodeId != null && !selectedNeighborIds.has(node.id);
      const nodeColor = isDimmed
        ? "rgba(148,163,184,0.25)"
        : isSelected
        ? SELECTED_COLOR
        : node.color || "#6b7280";

      let clusterMatchCount = 0;
      if (node.isCluster) {
        clusterMatchCount =
          serverMatchedClusterLabels.get(node.id) ??
          serverMatchedClusterLabels.get(node.label) ??
          0;
      }
      const isClusterMatch = clusterMatchCount > 0;

      const degree = degreeMap.get(node.id) || 0;

      if (node.isCluster) {
        const size = Math.max(8, Math.min(24, Math.sqrt(node.nodeCount || 10) * 2.5));
        if (isClusterMatch) {
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i - Math.PI / 6;
            const gs = size + 6;
            const px = node.x + gs * Math.cos(angle);
            const py = node.y + gs * Math.sin(angle);
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
        ctx.strokeStyle = isSelected
          ? SELECTED_COLOR
          : isClusterMatch
          ? "#ef4444"
          : CLUSTER_BORDER_COLOR;
        ctx.lineWidth = isClusterMatch ? 3 / globalScale : 2 / globalScale;
        ctx.stroke();
        const countText = isClusterMatch
          ? `${clusterMatchCount}/${node.nodeCount}`
          : `${node.nodeCount}`;
        const badgeFontSize = Math.max(8 / globalScale, 2);
        ctx.font = `bold ${badgeFontSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#fff";
        ctx.fillText(countText, node.x, node.y);
        if (showLabels && globalScale > LABEL_ZOOM_THRESHOLD && !isDimmed) {
          const lfs = Math.max(10 / globalScale, 1.5);
          ctx.font = `${lfs}px Inter, sans-serif`;
          ctx.textBaseline = "top";
          ctx.fillStyle = isClusterMatch ? "#dc2626" : "rgba(0,0,0,0.8)";
          ctx.fillText(node.name, node.x, node.y + size + 2);
        }
      } else {
        const baseR = isDense ? 4 : 5;
        const radius = baseR + Math.min(4, Math.sqrt(degree) * 0.8);
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
        ctx.fillStyle = nodeColor;
        ctx.fill();
        if (isSelected) {
          ctx.strokeStyle = SELECTED_COLOR;
          ctx.lineWidth = 2 / globalScale;
          ctx.stroke();
        }
        if (showLabels && globalScale > LABEL_ZOOM_THRESHOLD && !isDimmed) {
          const fontSize = Math.max(10 / globalScale, 1.5);
          ctx.font = `${fontSize}px Inter, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillStyle = "rgba(0,0,0,0.8)";
          ctx.fillText(node.name, node.x, node.y + radius + 2);
        }
      }
    },
    [
      selectedNodeId,
      selectedNeighborIds,
      degreeMap,
      showLabels,
      isDense,
      serverMatchedClusterLabels,
    ]
  );

  // ── Empty / loading states ─────────────────────────────────────────────────
  if (loading) {
    return (
      <CardSection className="flex w-full flex-col min-h-[700px] items-center justify-center">
        <ThreeDotsLoader />
      </CardSection>
    );
  }

  if (!scalableData || scalableData.nodes.length === 0) {
    return (
      <CardSection className="flex w-full flex-col gap-2 min-h-[200px] items-center justify-center">
        <Text as="p" headingH3 text05>Graph Explorer</Text>
        <Text as="p" mainContentBody text04 className="text-center max-w-sm">
          No graph data available. Select a collection and build a knowledge
          graph to visualize entities and relationships.
        </Text>
      </CardSection>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-08 border border-border-01 bg-background-tint-00 overflow-hidden",
        isFullscreen
          ? "fixed inset-4 z-50 shadow-xl"
          : "w-full min-h-[700px]"
      )}
    >
      {/* Toolbar */}
      <div className="flex flex-col gap-2 px-3 pt-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <Text as="p" mainUiAction text04 className="text-sm font-medium">
              Graph Explorer
            </Text>
            <Text as="span" mainContentMuted text03 className="text-xs tabular-nums">
              {forceData.nodes.length} nodes · {forceData.links.length} edges
              {totalNodes > forceData.nodes.length && (
                <>
                  {" "}(total:{" "}
                  {totalNodes.toLocaleString()} ·{" "}
                  {totalEdges.toLocaleString()})
                </>
              )}
            </Text>
            {currentMode !== "full" && (
              <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border border-status-warning-03 bg-status-warning-01 text-status-warning-07 uppercase">
                {currentMode}
              </span>
            )}
            {!enablePointer && (
              <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border border-status-error-03 bg-status-error-01 text-status-error-07">
                perf mode
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {/* 2D / 3D toggle */}
            <button
              onClick={handleToggle3D}
              title={is3D ? "Switch to 2D" : "Switch to 3D"}
              className={cn(
                "rounded-04 px-2 py-1 text-xs font-medium border transition-colors",
                is3D
                  ? "border-theme-primary-04 bg-theme-primary-01 text-theme-primary-07"
                  : "border-border-01 bg-background-tint-00 hover:bg-background-neutral-01 text-text-04"
              )}
            >
              {is3D ? "3D" : "2D"}
            </button>
            <div className="mx-1 h-4 w-px bg-border-01" />
            <button
              onClick={handleZoomIn}
              className="rounded-04 p-1 hover:bg-background-neutral-01 transition-colors"
              title="Zoom in"
            >
              <SvgZoomIn className="h-4 w-4 stroke-text-03" />
            </button>
            <button
              onClick={handleZoomOut}
              className="rounded-04 p-1 hover:bg-background-neutral-01 transition-colors"
              title="Zoom out"
            >
              <SvgZoomOut className="h-4 w-4 stroke-text-03" />
            </button>
            <button
              onClick={handleReset}
              className="rounded-04 p-1 hover:bg-background-neutral-01 transition-colors"
              title="Reset view"
            >
              <SvgRefreshCw className="h-4 w-4 stroke-text-03" />
            </button>
            <button
              onClick={() => setIsFullscreen((f) => !f)}
              className="rounded-04 p-1 hover:bg-background-neutral-01 transition-colors"
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? (
                <SvgFold className="h-4 w-4 stroke-text-03" />
              ) : (
                <SvgMaximize2 className="h-4 w-4 stroke-text-03" />
              )}
            </button>
          </div>
        </div>

        {/* Breadcrumbs */}
        {breadcrumbs.length > 0 && (
          <div className="flex items-center gap-1 text-xs flex-wrap">
            <button
              onClick={handleBackToOverview}
              className="flex items-center gap-0.5 text-theme-primary-05 hover:underline"
            >
              <SvgExpand className="h-3 w-3 stroke-theme-primary-05" />
              Overview
            </button>
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-0.5">
                <SvgChevronRight className="h-3 w-3 stroke-text-03" />
                <button
                  onClick={() => handleBreadcrumbClick(i)}
                  className={cn(
                    "hover:underline",
                    i === breadcrumbs.length - 1
                      ? "text-text-04 font-medium"
                      : "text-theme-primary-05"
                  )}
                >
                  {crumb.displayName}
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Search */}
        <div className="max-w-xs">
          <InputTypeIn
            placeholder="Search nodes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            leftSearchIcon={!searchLoading}
          />
          {serverClusterMatches && serverMatchedClusterLabels.size > 0 && (
            <Text as="p" mainContentMuted text03 className="mt-1 text-[11px]">
              {serverMatchedClusterLabels.size} cluster matched — highlighted in red
            </Text>
          )}
        </div>
      </div>

      {/* Canvas area */}
      <div
        className={cn(
          "relative overflow-hidden flex-1",
          isFullscreen ? "h-[calc(100vh-180px)]" : "min-h-[580px]"
        )}
      >
        <div ref={containerRef} className="absolute inset-0">
          {/* 2D renderer */}
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
              nodeRelSize={5}
              nodeVal={(node: ForceGraphNode) => node.val || 3}
              linkLabel={(link: ForceGraphLink) =>
                (link.relationshipTypes as string[] | undefined)?.length
                  ? `${link.type} (${(link.relationshipTypes as string[]).join(", ")})`
                  : link.type
              }
              nodeCanvasObject={nodeCanvasObject}
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
              linkWidth={getLinkWidth}
              linkColor={getLinkColor}
              backgroundColor="transparent"
            />
          )}

          {/* 3D renderer */}
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
                return (node.val || 3) + Math.min(4, Math.sqrt(deg) * 0.8);
              }}
              nodeColor={(node: ForceGraphNode) => {
                if (selectedNodeId && !selectedNeighborIds.has(node.id))
                  return "rgba(148,163,184,0.25)";
                return node.id === selectedNodeId
                  ? SELECTED_COLOR
                  : node.color || "#6b7280";
              }}
              linkLabel={(link: ForceGraphLink) => link.type}
              linkColor={getLinkColor}
              linkWidth={getLinkWidth}
              linkCurvature={(link: any) => {
                const idx = filteredData.links.indexOf(link);
                return parallelLinkMeta.get(idx) ?? 0;
              }}
              linkDirectionalArrowLength={isDense ? 2.5 : 4}
              linkDirectionalArrowRelPos={1}
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

          {/* 2D loading placeholder */}
          {!is3D && !ForceGraph2D && (
            <div className="flex h-full items-center justify-center">
              <ThreeDotsLoader />
            </div>
          )}

          {/* Settling overlay */}
          <div
            className={cn(
              "absolute inset-0 z-10 flex items-center justify-center bg-background-tint-00/80 backdrop-blur-sm transition-opacity duration-500",
              settling ? "opacity-100" : "opacity-0 pointer-events-none"
            )}
          >
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-theme-primary-04 border-t-transparent" />
              <Text as="span" mainContentMuted text03 className="text-sm">
                Settling layout…
              </Text>
            </div>
          </div>

          {/* Interaction hint */}
          <div className="absolute bottom-2 left-2 select-none pointer-events-none">
            <Text as="p" mainContentMuted text03 className="text-[10px] opacity-60">
              {currentMode === "overview" &&
                "Click cluster to expand · Right-click node for neighborhood"}
              {currentMode === "expand" &&
                "Viewing cluster contents · Right-click for neighborhood"}
              {currentMode === "neighborhood" && "Ego-graph view · Click nodes to explore"}
              {currentMode === "full" &&
                forceData.nodes.length > 200 &&
                "Large graph — zoom to see labels · Right-click for neighborhood"}
            </Text>
          </div>
        </div>
      </div>
    </div>
  );
}
