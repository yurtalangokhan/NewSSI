"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Network, Hammer, Search as SearchIcon, Loader2 } from "lucide-react";
import { GraphExplorer } from "./components/graph-explorer";
import { GraphStatsCard } from "./components/graph-stats-card";
import { BuildPipeline } from "./components/build-pipeline";
import { GraphSearch } from "./components/graph-search";
import { EntityPreview } from "./components/entity-preview";
import { useGraphData, useGraphCollectionIds } from "./hooks/use-graph-rag";
import { useRagContext } from "@/features/rag/providers/RAG";
import { useDataSources } from "@/hooks/use-datasources";
import { useAuthContext } from "@/providers/Auth";
import type { GraphNode } from "@/types/graph";

export default function GraphRAGInterface() {
  const { collections, getCollections, setCollections } = useRagContext();
  const { dataSources, loading: dsLoading } = useDataSources();
  const { session } = useAuthContext();
  const {
    graphData,
    stats,
    loading,
    fetchGraphData,
    fetchStats,
    fetchLabelsPaginated,
    fetchRelTypesPaginated,
  } = useGraphData();
  const { graphCollectionIds, loadingIds, fetchGraphCollectionIds } =
    useGraphCollectionIds();

  const [selectedCollectionId, setSelectedCollectionId] = useState<string>("");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [activeTab, setActiveTab] = useState<string>("explorer");
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set());
  const [selectedRelTypes, setSelectedRelTypes] = useState<Set<string>>(new Set());

  // Whether the dropdown data is still loading
  const dropdownLoading = dsLoading || loadingIds;

  // Merge collections + data sources into one deduplicated list,
  // then filter to only those that already have a graph built.
  const graphSources = useMemo(() => {
    const map = new Map<string, { id: string; name: string; isDataSource: boolean }>();
    for (const c of collections) {
      map.set(c.uuid, { id: c.uuid, name: c.name, isDataSource: false });
    }
    for (const ds of dataSources) {
      if (!map.has(ds.id)) {
        map.set(ds.id, { id: ds.id, name: ds.name, isDataSource: true });
      } else {
        map.set(ds.id, { ...map.get(ds.id)!, isDataSource: true });
      }
    }
    // Only keep sources that have a graph built
    return Array.from(map.values()).filter((s) => graphCollectionIds.has(s.id));
  }, [collections, dataSources, graphCollectionIds]);

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

  // Refresh collections + graph-built IDs on mount
  useEffect(() => {
    if (!session?.accessToken) return;
    getCollections(session.accessToken).then((cols) => {
      if (cols.length > 0) setCollections(cols);
    });
    fetchGraphCollectionIds();
  }, [session?.accessToken]);

  // Load graph data when collection changes
  useEffect(() => {
    if (!selectedCollectionId) return;
    fetchGraphData(selectedCollectionId);
    fetchStats(selectedCollectionId);
  }, [selectedCollectionId]);

  const handleBuildComplete = useCallback(() => {
    // Refresh graph-built IDs so the new graph appears in the dropdown
    fetchGraphCollectionIds();
    if (!selectedCollectionId) return;
    fetchGraphData(selectedCollectionId);
    fetchStats(selectedCollectionId);
  }, [selectedCollectionId, fetchGraphData, fetchStats, fetchGraphCollectionIds]);

  const handleNodeSelect = useCallback((node: GraphNode) => {
    setSelectedNode(node);
  }, []);

  return (
    <div className="w-full px-4 py-4 space-y-4">
      {/* Collection selector */}
      <div className="flex items-end gap-4">
        <div className="w-full max-w-sm space-y-1.5">
          <Label className="text-xs text-muted-foreground">
            Select a collection to explore its knowledge graph
          </Label>
          <Select
            value={selectedCollectionId}
            onValueChange={(v) => {
              setSelectedCollectionId(v);
              setSelectedNode(null);
              setSelectedLabels(new Set());
              setSelectedRelTypes(new Set());
            }}
            disabled={dropdownLoading}
          >
            <SelectTrigger>
              {dropdownLoading ? (
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading collections...
                </span>
              ) : (
                <SelectValue placeholder="Choose collection..." />
              )}
            </SelectTrigger>
            <SelectContent>
              {!dropdownLoading && graphSources.length === 0 && (
                <div className="px-2 py-1.5 text-sm text-muted-foreground">
                  No collections with a knowledge graph yet.
                  Use the Build tab first.
                </div>
              )}
              {graphSources.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  <span className="flex items-center gap-2">
                    {s.name}
                    {s.isDataSource && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        data source
                      </Badge>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Stats summary */}
        {stats && selectedCollectionId && (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span>{stats.node_count} nodes</span>
            <span>·</span>
            <span>{stats.edge_count} edges</span>
            <span>·</span>
            <span>{Object.keys(stats.label_counts).length} labels</span>
          </div>
        )}
      </div>

      {/* Main tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full max-w-2xl grid-cols-3">
          <TabsTrigger value="explorer" className="flex items-center gap-2">
            <Network className="h-4 w-4" />
            Graph Explorer
          </TabsTrigger>
          <TabsTrigger value="build" className="flex items-center gap-2">
            <Hammer className="h-4 w-4" />
            Build
          </TabsTrigger>
          <TabsTrigger value="search" className="flex items-center gap-2">
            <SearchIcon className="h-4 w-4" />
            Search
          </TabsTrigger>
        </TabsList>

        {/* ─── Graph Explorer Tab ─────────────────────────── */}
        <TabsContent value="explorer" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-4">
            {/* Graph visualization */}
            <div className="lg:col-span-3 flex">
              <GraphExplorer
                graphData={graphData}
                loading={loading}
                onNodeClick={handleNodeSelect}
                selectedLabels={selectedLabels}
                selectedRelTypes={selectedRelTypes}
              />
            </div>

            {/* Side panel: stats with clickable filters */}
            <div className="lg:col-span-1">
              {stats && (
                <GraphStatsCard
                  stats={stats}
                  collectionId={selectedCollectionId}
                  selectedLabels={selectedLabels}
                  selectedRelTypes={selectedRelTypes}
                  onToggleLabel={handleToggleLabel}
                  onToggleRelType={handleToggleRelType}
                  fetchLabelsPaginated={fetchLabelsPaginated}
                  fetchRelTypesPaginated={fetchRelTypesPaginated}
                />
              )}
            </div>
          </div>

          {/* Entity preview – horizontal below the explorer */}
          {selectedNode && graphData && (
            <EntityPreview
              node={selectedNode}
              edges={graphData.edges}
              nodes={graphData.nodes}
              onClose={() => setSelectedNode(null)}
              onNodeSelect={handleNodeSelect}
            />
          )}
        </TabsContent>

        {/* ─── Build Tab ──────────────────────────────────── */}
        <TabsContent value="build" className="mt-4">
          <div className="max-w-2xl">
            <BuildPipeline onBuildComplete={handleBuildComplete} />
          </div>
        </TabsContent>

        {/* ─── Search Tab ─────────────────────────────────── */}
        <TabsContent value="search" className="mt-4">
          {selectedCollectionId ? (
            <div className="max-w-3xl">
              <GraphSearch
                collectionId={selectedCollectionId}
                onNodeSelect={(node) => {
                  handleNodeSelect(node);
                  setActiveTab("explorer");
                }}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a collection above to search its knowledge graph.
            </p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
