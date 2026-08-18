"use client";

import React, { useState, useCallback, useMemo, useRef } from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { redirect } from "next/navigation";
import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import Tabs from "@/refresh-components/Tabs";
import { useIsKGExposed } from "@/app/admin/kg/utils";
import {
  useCollections,
  useGraphCollections,
  fetchScalableGraphData,
  fetchFlatGraphData,
  isClusterNode,
  isClusterEdge,
  type ClusteredGraphData,
  type GraphData,
  type GraphNode,
  type GraphEdge,
} from "@/lib/langconnect";
import { useAirbyteDatasources } from "@/lib/airbyte";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import GraphBuildPanel from "@/app/admin/kg/components/GraphBuildPanel";
import GraphSearchPanel from "@/app/admin/kg/components/GraphSearchPanel";
import GraphExplorer from "@/app/admin/kg/components/GraphExplorer";
import GraphStatsCard from "@/app/admin/kg/components/GraphStatsCard";
import EntityPreview from "@/app/admin/kg/components/EntityPreview";
import { ThreeDotsLoader } from "@/components/Loading";
import { SvgActivity, SvgSearch, SvgNetworkGraph } from "@opal/icons";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.KNOWLEDGE_GRAPH]!;

// Tabs that require a collection to be selected
const COLLECTION_REQUIRED_TABS = new Set(["explorer", "search"]);

// ── Collection selector ────────────────────────────────────────────────────

function NoGraphBadge() {
  const { t } = useTranslation();
  return (
    <span className="ml-1.5 inline-flex items-center rounded-04 border border-status-warning-03 bg-status-warning-01 px-1.5 py-0.5 text-[10px] font-medium leading-none text-status-warning-06">
      {t("admin.kg.noGraph")}
    </span>
  );
}

function CollectionSelector({
  selectedId,
  onSelect,
  highlight,
}: {
  selectedId: string | null;
  onSelect: (id: string | null, hasGraph: boolean) => void;
  highlight?: boolean;
}) {
  const { t } = useTranslation();
  const { collections, isLoading: collectionsLoading } = useCollections();
  const { datasources, isLoading: dsLoading } = useAirbyteDatasources();
  const { graphCollections, isLoading: graphLoading } = useGraphCollections();

  const isLoading = collectionsLoading || dsLoading || graphLoading;

  const graphCollectionSet = useMemo(
    () => new Set(graphCollections),
    [graphCollections]
  );

  // Datasource IDs — used to separate pure RAG collections from datasource-backed ones
  const datasourceIdSet = useMemo(
    () => new Set(datasources.map((ds) => ds.id)),
    [datasources]
  );

  // Pure RAG collections (not backed by a datasource)
  const ragCollections = useMemo(
    () => collections.filter((c) => !datasourceIdSet.has(c.uuid)),
    [collections, datasourceIdSet]
  );

  // Datasources merged with any matching collection entry for display name
  const datasourceItems = useMemo(() => {
    const collectionNameMap = new Map(collections.map((c) => [c.uuid, c.name]));
    return datasources.map((ds) => ({
      id: ds.id,
      // Prefer the datasource's own name; fall back to collection name if set
      name: ds.name || collectionNameMap.get(ds.id) || ds.connector_display_name || "Unnamed",
      hasGraph: graphCollectionSet.has(ds.id),
    }));
  }, [datasources, collections, graphCollectionSet]);

  const hasUnbuilt =
    ragCollections.some((c) => !graphCollectionSet.has(c.uuid)) ||
    datasourceItems.some((ds) => !ds.hasGraph);

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
        {t("admin.kg.collection")}
      </Text>
      <Text as="p" mainContentBody text04>
        {t("admin.kg.collectionDescription")}
      </Text>
      <div className="w-full max-w-sm">
        <InputSelect
          value={selectedId ?? ""}
          onValueChange={(id) => {
            const val = id || null;
            onSelect(val, val ? graphCollectionSet.has(val) : false);
          }}
          error={highlight}
        >
          <InputSelect.Trigger placeholder={t("admin.kg.selectCollectionPlaceholder")} />
          <InputSelect.Content>
            {ragCollections.length > 0 && (
              <InputSelect.Group>
                <InputSelect.Label>{t("admin.kg.collections")}</InputSelect.Label>
                {ragCollections.map((c) => {
                  const hasGraph = graphCollectionSet.has(c.uuid);
                  return (
                    <InputSelect.Item key={c.uuid} value={c.uuid}>
                      <span className="flex items-center">
                        {c.name}
                        {!hasGraph && <NoGraphBadge />}
                      </span>
                    </InputSelect.Item>
                  );
                })}
              </InputSelect.Group>
            )}
            {datasourceItems.length > 0 && (
              <InputSelect.Group>
                <InputSelect.Label>{t("admin.kg.dataSources")}</InputSelect.Label>
                {datasourceItems.map((ds) => (
                  <InputSelect.Item key={ds.id} value={ds.id}>
                    <span className="flex items-center">
                      {ds.name}
                      {!ds.hasGraph && <NoGraphBadge />}
                    </span>
                  </InputSelect.Item>
                ))}
              </InputSelect.Group>
            )}
          </InputSelect.Content>
        </InputSelect>
      </div>
      {highlight && (
        <Text as="p" className="text-xs text-status-error-06 font-medium">
          {!selectedId
            ? t("admin.kg.selectCollectionForTab")
            : t("admin.kg.noBuiltGraph")}
        </Text>
      )}
      {!highlight && hasUnbuilt && (
        <Text as="p" mainContentMuted text03 className="text-xs">
          {t("admin.kg.noGraphHintPrefix")} <span className="inline-flex items-center rounded-04 border border-status-warning-03 bg-status-warning-01 px-1 text-[10px] font-medium text-status-warning-06">{t("admin.kg.noGraph")}</span> {t("admin.kg.noGraphHintSuffix")} <strong>{t("admin.kg.buildTab")}</strong>.
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
  const { t } = useTranslation();
  const [scalableData, setScalableData] = useState<ClusteredGraphData | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set());
  const [selectedRelTypes, setSelectedRelTypes] = useState<Set<string>>(new Set());
  const [visibleCounts, setVisibleCounts] = useState({ nodeCount: 0, edgeCount: 0 });

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

  // Shared: set loading, clear selection/filters, fetch scalable data, update state.
  const loadScalable = useCallback(
    async (params?: Parameters<typeof fetchScalableGraphData>[1]) => {
      if (!collectionId) return;
      setExplorerLoading(true);
      setSelectedLabels(new Set());
      setSelectedRelTypes(new Set());
      setSelectedNode(null);
      try {
        const data = await fetchScalableGraphData(collectionId, params);
        setScalableData(data);
      } catch { /* ignore */ } finally {
        setExplorerLoading(false);
      }
    },
    [collectionId]
  );

  const handleClusterExpand = useCallback(
    (clusterLabel: string) =>
      loadScalable({ mode: "expand", clusterLabel, nodeLimit: 200, edgeLimit: 500 }),
    [loadScalable]
  );

  const handleNeighborhoodRequest = useCallback(
    (nodeId: string) => loadScalable({ mode: "neighborhood", nodeId }),
    [loadScalable]
  );

  const handleBackToOverview = useCallback(
    () => loadScalable(),
    [loadScalable]
  );

  // Entity-label filter options: reported by GraphExplorer from the nodes
  // that actually survive the current relationship-type filter, so the list
  // never offers a label with no visible nodes/clusters to show, and stays
  // in sync with the relationship-type filter instead of listing every
  // label loaded in the whole (unfiltered) view.
  const [availableLabels, setAvailableLabels] = useState<
    { name: string; count: number }[]
  >([]);

  // Relationship-type filter options: reported by GraphExplorer from the
  // edges (or, in overview/sub-cluster views with no real edges, each
  // cluster's `_rel_type_counts` aggregate) that actually survive the
  // current label filter — instead of a separately-scoped backend query
  // that could list types belonging to no edge visible in the current view.
  const [availableRelTypes, setAvailableRelTypes] = useState<
    { name: string; count: number }[]
  >([]);

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
          {t("admin.kg.selectCollectionToExplore")}
        </Text>
      </CardSection>
    );
  }

  const visibleNodes = visibleCounts.nodeCount;
  const visibleEdges = visibleCounts.edgeCount;
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
            onLabelFacetCountsChange={setAvailableLabels}
            onRelTypeFacetCountsChange={setAvailableRelTypes}
            onVisibleCountsChange={setVisibleCounts}
          />
        </div>
        <div className="lg:col-span-1">
          <GraphStatsCard
            collectionId={collectionId}
            availableLabels={availableLabels}
            availableRelTypes={availableRelTypes}
            selectedLabels={selectedLabels}
            selectedRelTypes={selectedRelTypes}
            onToggleLabel={handleToggleLabel}
            onToggleRelType={handleToggleRelType}
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
        const previewNodes: GraphNode[] = useScalable
          ? scalableData!.nodes.filter((n): n is GraphNode => !isClusterNode(n))
          : (graphData?.nodes ?? []);
        const previewEdges: GraphEdge[] = useScalable
          ? scalableData!.edges.filter((e): e is GraphEdge => !isClusterEdge(e))
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
  const { t } = useTranslation();
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [selectorHighlight, setSelectorHighlight] = useState(false);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined
  );
  const { collections } = useCollections();
  const { datasources } = useAirbyteDatasources();
  const { graphCollections } = useGraphCollections();

  // Derived from the shared SWR-backed `graphCollections` list (not local
  // state captured at selection time) so it updates immediately once a
  // build completes and revalidates that cache — no page refresh needed.
  const selectedHasGraph = useMemo(
    () => !!collectionId && graphCollections.includes(collectionId),
    [collectionId, graphCollections]
  );

  const datasourceIdSet = useMemo(
    () => new Set(datasources.map((ds) => ds.id)),
    [datasources]
  );
  const ragCollectionCount = useMemo(
    () =>
      collections.filter(
        (collection) => !datasourceIdSet.has(collection.uuid)
      ).length,
    [collections, datasourceIdSet]
  );
  const knowledgeSourceCount = ragCollectionCount + datasources.length;
  const graphReadyCount = graphCollections.length;
  const needsGraphCount = Math.max(knowledgeSourceCount - graphReadyCount, 0);

  const triggerCollectionRequired = useCallback(() => {
    setSelectorHighlight(true);
    clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(
      () => setSelectorHighlight(false),
      1800
    );
  }, []);

  const handleCollectionSelect = useCallback(
    (id: string | null, _hasGraph: boolean) => {
      setCollectionId(id);
      if (id) {
        setSelectorHighlight(false);
        clearTimeout(highlightTimerRef.current);
      }
    },
    []
  );

  const handleTabChange = useCallback(
    (value: string) => {
      // Block restricted tabs when no collection selected or collection has no graph
      if (
        COLLECTION_REQUIRED_TABS.has(value) &&
        (!collectionId || !selectedHasGraph)
      ) {
        triggerCollectionRequired();
        return;
      }
      onTabChange(value);
    },
    [collectionId, selectedHasGraph, triggerCollectionRequired, onTabChange]
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
      <AdminOverviewPanel
        icon={route.icon}
        title={t("admin.kg.workspaceTitle")}
        description={t("admin.kg.workspaceDescription")}
        metrics={[
          {
            label: t("admin.kg.knowledgeSourcesMetricLabel"),
            value: String(knowledgeSourceCount),
            tone: knowledgeSourceCount > 0 ? "success" : "warning",
          },
          {
            label: t("admin.kg.graphReadyMetricLabel"),
            value: String(graphReadyCount),
            tone: graphReadyCount > 0 ? "success" : "neutral",
          },
          {
            label: t("admin.kg.needsGraphMetricLabel"),
            value: String(needsGraphCount),
            tone: needsGraphCount > 0 ? "warning" : "success",
          },
          {
            label: t("admin.kg.dataSourcesMetricLabel"),
            value: String(datasources.length),
          },
        ]}
        actions={[
          {
            label: t("admin.navigation.routes.documentProcessing.sidebar"),
            href: ADMIN_PATHS.DOCUMENT_PROCESSING,
          },
          {
            label: t("admin.navigation.routes.documentExplorer.sidebar"),
            href: ADMIN_PATHS.DOCUMENT_EXPLORER,
            primary: true,
          },
        ]}
      />

      <Text as="p" text03>
        {t("admin.kg.description")}
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
            disabled={!collectionId || !selectedHasGraph}
            onClick={() =>
              (!collectionId || !selectedHasGraph) &&
              triggerCollectionRequired()
            }
          >
            {t("admin.kg.graphExplorerTab")}
          </Tabs.Trigger>
          <Tabs.Trigger value="build" icon={SvgActivity}>
            {t("admin.kg.buildTab")}
          </Tabs.Trigger>
          <Tabs.Trigger
            value="search"
            icon={SvgSearch}
            disabled={!collectionId || !selectedHasGraph}
            onClick={() =>
              (!collectionId || !selectedHasGraph) &&
              triggerCollectionRequired()
            }
          >
            {t("admin.kg.searchTab")}
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
  const { t } = useTranslation();
  const { kgExposed, isLoading } = useIsKGExposed();
  const [activeTab, setActiveTab] = useState("build");

  if (isLoading) return <></>;
  if (!kgExposed) redirect("/");

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={t("admin.kg.pageDescription", {
          defaultValue:
            "Build, inspect, and search entity graphs across your indexed knowledge sources.",
        })}
        separator
      />
      <SettingsLayouts.Body>
        <Main activeTab={activeTab} onTabChange={setActiveTab} />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
