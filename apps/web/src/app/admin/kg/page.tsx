"use client";

import React, { useState, useCallback, useMemo, useRef } from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { redirect } from "next/navigation";
import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import Tabs from "@/refresh-components/Tabs";
import { useIsKGExposed } from "@/app/admin/kg/utils";
import { useCollections, useGraphCollections } from "@/lib/langconnect";
import {
  fetchScalableGraphData,
  fetchFlatGraphData,
  type ClusteredGraphData,
  type GraphData,
  type GraphNode,
} from "@/lib/langconnect";
import { useAirbyteDatasources } from "@/lib/airbyte";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import GraphBuildPanel from "@/app/admin/kg/components/GraphBuildPanel";
import GraphSearchPanel from "@/app/admin/kg/components/GraphSearchPanel";
import GraphExplorer from "@/app/admin/kg/components/GraphExplorer";
import GraphStatsCard from "@/app/admin/kg/components/GraphStatsCard";
import EntityPreview from "@/app/admin/kg/components/EntityPreview";
import { ThreeDotsLoader } from "@/components/Loading";
import { SvgActivity, SvgSearch, SvgNetworkGraph } from "@opal/icons";
import { cn } from "@/lib/utils";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.KNOWLEDGE_GRAPH]!;

// Tabs that require a collection to be selected
const COLLECTION_REQUIRED_TABS = new Set(["explorer", "search"]);

// ── Collection selector ────────────────────────────────────────────────────

function CollectionSelector({
  selectedId,
  onSelect,
  highlight,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  highlight?: boolean;
}) {
  const { collections, isLoading: collectionsLoading } = useCollections();
  const { datasources, isLoading: dsLoading } = useAirbyteDatasources();
  const { graphCollections, isLoading: graphLoading } = useGraphCollections();

  const isLoading = collectionsLoading || dsLoading || graphLoading;

  const graphCollectionSet = useMemo(
    () => new Set(graphCollections),
    [graphCollections]
  );

  const allSources = useMemo(() => {
    const map = new Map<
      string,
      { id: string; name: string; isDataSource: boolean }
    >();
    for (const c of collections) {
      map.set(c.uuid, { id: c.uuid, name: c.name, isDataSource: false });
    }
    for (const ds of datasources) {
      if (!map.has(ds.id)) {
        map.set(ds.id, { id: ds.id, name: ds.name, isDataSource: true });
      } else {
        map.set(ds.id, { ...map.get(ds.id)!, isDataSource: true });
      }
    }
    return Array.from(map.values());
  }, [collections, datasources]);

  const hasUnbuilt = allSources.some((s) => !graphCollectionSet.has(s.id));

  if (isLoading) {
    return (
      <CardSection>
        <ThreeDotsLoader />
      </CardSection>
    );
  }

  return (
    <CardSection className="flex flex-col gap-3">
      <Text as="p" headingH3 text05>
        Collection
      </Text>
      <Text as="p" mainContentBody text04>
        Select a collection with a built knowledge graph to explore and run
        graph searches.
      </Text>
      <select
        className={cn(
          "w-full max-w-sm rounded-08 border px-3 py-2 text-sm text-text-04 focus:outline-none transition-all duration-300",
          highlight
            ? "border-status-error-04 ring-2 ring-status-error-04 bg-status-error-01"
            : "border-border-01 bg-background-tint-00 focus:ring-1 focus:ring-theme-primary-04"
        )}
        value={selectedId ?? ""}
        onChange={(e) => onSelect(e.target.value || null)}
      >
        <option value="">— Select a collection —</option>
        {allSources.map((s) => {
          const hasGraph = graphCollectionSet.has(s.id);
          return (
            <option key={s.id} value={s.id} disabled={!hasGraph}>
              {s.name}{s.isDataSource ? " [data source]" : ""}
            </option>
          );
        })}
      </select>
      {highlight && (
        <Text as="p" className="text-xs text-status-error-06 font-medium">
          Please select a collection to use this tab.
        </Text>
      )}
      {!highlight && hasUnbuilt && (
        <Text as="p" mainContentMuted text03 className="text-xs">
          Collections without a built graph are disabled. Go to the{" "}
          <strong>Build</strong> tab to build a graph.
        </Text>
      )}
    </CardSection>
  );
}

// ── Explorer tab content (graph + side panel + entity preview) ─────────────

function ExplorerTab({
  collectionId,
  isActive,
}: {
  collectionId: string | null;
  isActive: boolean;
}) {
  const [scalableData, setScalableData] = useState<ClusteredGraphData | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set());
  const [selectedRelTypes, setSelectedRelTypes] = useState<Set<string>>(new Set());

  const loadData = useCallback(async (id: string) => {
    setExplorerLoading(true);
    setSelectedNode(null);
    setSelectedLabels(new Set());
    setSelectedRelTypes(new Set());
    try {
      const [scalable, flat] = await Promise.all([
        fetchScalableGraphData(id),
        fetchFlatGraphData(id),
      ]);
      setScalableData(scalable);
      setGraphData(flat);
    } catch {
      // ignore – user will see empty state
    } finally {
      setExplorerLoading(false);
    }
  }, []);

  const prevIdRef = React.useRef<string | null>(null);
  if (collectionId !== prevIdRef.current) {
    prevIdRef.current = collectionId;
    if (collectionId) {
      loadData(collectionId);
    } else {
      setScalableData(null);
      setGraphData(null);
    }
  }

  const handleClusterExpand = useCallback(
    async (clusterLabel: string) => {
      if (!collectionId) return;
      setExplorerLoading(true);
      setSelectedLabels(new Set());
      setSelectedRelTypes(new Set());
      setSelectedNode(null);
      try {
        const data = await fetchScalableGraphData(collectionId, {
          mode: "expand",
          clusterLabel,
          nodeLimit: 200,
          edgeLimit: 500,
        });
        setScalableData(data);
      } catch { /* ignore */ } finally {
        setExplorerLoading(false);
      }
    },
    [collectionId]
  );

  const handleNeighborhoodRequest = useCallback(
    async (nodeId: string) => {
      if (!collectionId) return;
      setExplorerLoading(true);
      setSelectedLabels(new Set());
      setSelectedRelTypes(new Set());
      setSelectedNode(null);
      try {
        const data = await fetchScalableGraphData(collectionId, {
          mode: "neighborhood",
          nodeId,
        });
        setScalableData(data);
      } catch { /* ignore */ } finally {
        setExplorerLoading(false);
      }
    },
    [collectionId]
  );

  const handleBackToOverview = useCallback(async () => {
    if (!collectionId) return;
    setExplorerLoading(true);
    setSelectedLabels(new Set());
    setSelectedRelTypes(new Set());
    setSelectedNode(null);
    try {
      const data = await fetchScalableGraphData(collectionId);
      setScalableData(data);
    } catch { /* ignore */ } finally {
      setExplorerLoading(false);
    }
  }, [collectionId]);

  const handleToggleLabel = useCallback((label: string) => {
    setSelectedLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }, []);

  const handleToggleRelType = useCallback((relType: string) => {
    setSelectedRelTypes((prev) => {
      const next = new Set(prev);
      if (next.has(relType)) next.delete(relType);
      else next.add(relType);
      return next;
    });
  }, []);

  if (!collectionId) {
    return (
      <CardSection className="flex items-center justify-center py-12">
        <Text as="p" mainContentMuted text03>
          Select a collection above to explore its knowledge graph.
        </Text>
      </CardSection>
    );
  }

  const visibleNodes = scalableData?.nodes.length ?? 0;
  const visibleEdges = scalableData?.edges.length ?? 0;
  const totalNodes = scalableData?.total_node_count ?? 0;
  const totalEdges = scalableData?.total_edge_count ?? 0;

  return (
    <div className="flex flex-col gap-4 w-full">
      {/* 3:1 grid — graph left, stats right */}
      <div className="grid w-full grid-cols-1 gap-4 lg:grid-cols-4 items-stretch">
        <div className="lg:col-span-3">
          <GraphExplorer
            scalableData={scalableData}
            graphData={graphData}
            loading={explorerLoading}
            collectionId={collectionId}
            onNodeClick={setSelectedNode}
            onClusterExpand={handleClusterExpand}
            onNeighborhoodRequest={handleNeighborhoodRequest}
            onBackToOverview={handleBackToOverview}
            selectedLabels={selectedLabels}
            selectedRelTypes={selectedRelTypes}
            isActive={isActive}
          />
        </div>
        <div className="lg:col-span-1">
          <GraphStatsCard
            collectionId={collectionId}
            selectedLabels={selectedLabels}
            selectedRelTypes={selectedRelTypes}
            onToggleLabel={handleToggleLabel}
            onToggleRelType={handleToggleRelType}
            scopeLabel={scalableData?.scope_label ?? undefined}
            totalNodes={totalNodes}
            totalEdges={totalEdges}
            visibleNodes={visibleNodes}
            visibleEdges={visibleEdges}
          />
        </div>
      </div>

      {/* Entity preview below the graph */}
      {selectedNode && (() => {
        // In expand/neighborhood/full mode the scalableData contains the
        // actual individual nodes + edges for the current view. Use that
        // instead of the limited flat graphData so all connections show.
        const useScalable =
          scalableData &&
          scalableData.mode !== "overview" &&
          scalableData.nodes.some((n) => n.id === selectedNode.id);
        const previewNodes = useScalable
          ? (scalableData!.nodes.filter((n) => !("is_cluster" in n && n.is_cluster)) as import("@/lib/langconnect").GraphNode[])
          : (graphData?.nodes ?? []);
        const previewEdges = useScalable
          ? (scalableData!.edges.filter((e) => !("weight" in e && Array.isArray((e as any).relationship_types))) as import("@/lib/langconnect").GraphEdge[])
          : (graphData?.edges ?? []);
        if (!previewNodes.length && !graphData) return null;
        return (
          <EntityPreview
            node={selectedNode}
            edges={previewEdges}
            nodes={previewNodes}
            onClose={() => setSelectedNode(null)}
            onNodeSelect={setSelectedNode}
          />
        );
      })()}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

function Main({
  activeTab,
  onTabChange,
}: {
  activeTab: string;
  onTabChange: (tab: string) => void;
}) {
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [selectorHighlight, setSelectorHighlight] = useState(false);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const triggerCollectionRequired = useCallback(() => {
    setSelectorHighlight(true);
    clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(() => setSelectorHighlight(false), 1800);
  }, []);

  const handleCollectionSelect = useCallback((id: string | null) => {
    setCollectionId(id);
    if (id) {
      setSelectorHighlight(false);
      clearTimeout(highlightTimerRef.current);
    }
  }, []);

  const handleTabChange = useCallback(
    (value: string) => {
      // Block restricted tabs when no collection is selected
      if (COLLECTION_REQUIRED_TABS.has(value) && !collectionId) {
        triggerCollectionRequired();
        return;
      }
      onTabChange(value);
    },
    [collectionId, triggerCollectionRequired, onTabChange]
  );

  const handleBuildComplete = useCallback(
    () => {},
    []
  );

  const isExplorer = activeTab === "explorer";

  return (
    <div
      className="flex flex-col gap-y-6 mx-auto w-full"
      style={{
        maxWidth: isExplorer ? "100%" : "54.5rem",
        transition: "max-width 500ms ease-in-out",
      }}
    >
      <Text as="p" text03>
        Build a knowledge graph from your RAG collections. Extract entities and
        relationships from documents, explore the graph visually, and run
        graph-powered semantic searches.
      </Text>

      <CollectionSelector
        selectedId={collectionId}
        onSelect={handleCollectionSelect}
        highlight={selectorHighlight}
      />

      {/* Tabs — Build uses forceMount to preserve progress across tab switches */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <Tabs.List>
          <Tabs.Trigger
            value="explorer"
            icon={SvgNetworkGraph}
            disabled={!collectionId}
            onClick={() => !collectionId && triggerCollectionRequired()}
          >
            Graph Explorer
          </Tabs.Trigger>
          <Tabs.Trigger value="build" icon={SvgActivity}>
            Build
          </Tabs.Trigger>
          <Tabs.Trigger
            value="search"
            icon={SvgSearch}
            disabled={!collectionId}
            onClick={() => !collectionId && triggerCollectionRequired()}
          >
            Search
          </Tabs.Trigger>
        </Tabs.List>

        <Tabs.Content value="explorer">
          <ExplorerTab collectionId={collectionId} isActive={isExplorer} />
        </Tabs.Content>

        {/* forceMount keeps build state alive when switching tabs */}
        <TabsPrimitive.Content
          value="build"
          forceMount
          className="pt-4 focus:outline-none w-full data-[state=inactive]:hidden"
        >
          <GraphBuildPanel
            collectionId={collectionId}
            onBuildComplete={handleBuildComplete}
          />
        </TabsPrimitive.Content>

        <Tabs.Content value="search">
          <GraphSearchPanel collectionId={collectionId} />
        </Tabs.Content>
      </Tabs>
    </div>
  );
}

export default function Page() {
  const { kgExposed, isLoading } = useIsKGExposed();
  const [activeTab, setActiveTab] = useState("build");

  if (isLoading) return <></>;
  if (!kgExposed) redirect("/");

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header icon={route.icon} title={route.title} separator />
      <SettingsLayouts.Body>
        <Main activeTab={activeTab} onTabChange={setActiveTab} />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
