/**
 * Build Pipeline component – triggers knowledge graph construction from
 * a selected RAG collection and shows real-time progress.
 */

"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Loader2,
  Play,
  CheckCircle,
  AlertTriangle,
  Trash2,
  Sparkles,
  RefreshCw,
} from "lucide-react";
import { useGraphBuild, useGraphData, useGraphCollectionIds } from "../hooks/use-graph-rag";
import { useRagContext } from "@/features/rag/providers/RAG";
import { useDataSources } from "@/hooks/use-datasources";
import type { BuildStatusType } from "@/types/graph";

const STATUS_CONFIG: Record<
  BuildStatusType,
  { label: string; icon: React.ReactNode; color: string }
> = {
  pending: {
    label: "Pending",
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
    color: "text-yellow-500",
  },
  extracting: {
    label: "Extracting Entities",
    icon: <Sparkles className="h-4 w-4 animate-pulse" />,
    color: "text-blue-500",
  },
  building: {
    label: "Building Graph",
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
    color: "text-indigo-500",
  },
  completed: {
    label: "Completed",
    icon: <CheckCircle className="h-4 w-4" />,
    color: "text-green-500",
  },
  failed: {
    label: "Failed",
    icon: <AlertTriangle className="h-4 w-4" />,
    color: "text-red-500",
  },
};

interface BuildPipelineProps {
  onBuildComplete?: () => void;
}

export function BuildPipeline({ onBuildComplete }: BuildPipelineProps) {
  const { collections } = useRagContext();
  const { dataSources, loading: dsLoading } = useDataSources();
  const { startBuild, pollBuildStatus, buildProgress, setBuildProgress } =
    useGraphBuild();
  const { deleteGraph, fetchStats } = useGraphData();
  const { graphCollectionIds, loadingIds: _graphIdsLoading, fetchGraphCollectionIds } =
    useGraphCollectionIds();

  // Fetch graph collection IDs on mount so we know which ones are already built
  useEffect(() => {
    fetchGraphCollectionIds();
  }, [fetchGraphCollectionIds]);

  // Whether the dropdown data is still loading
  const sourcesLoading = dsLoading;

  // Merge collections + data sources into a single deduplicated list.
  // Data sources are also collections (same DB row) so we deduplicate by id.
  const allSources = useMemo(() => {
    const map = new Map<string, { id: string; name: string; isDataSource: boolean }>();
    for (const c of collections) {
      map.set(c.uuid, { id: c.uuid, name: c.name, isDataSource: false });
    }
    for (const ds of dataSources) {
      if (!map.has(ds.id)) {
        map.set(ds.id, { id: ds.id, name: ds.name, isDataSource: true });
      } else {
        // Mark existing entry as also a data source
        map.set(ds.id, { ...map.get(ds.id)!, isDataSource: true });
      }
    }
    return Array.from(map.values());
  }, [collections, dataSources]);

  const [selectedCollectionId, setSelectedCollectionId] = useState<string>("");
  const [entityTypes, setEntityTypes] = useState<string>("");
  const [relationshipTypes, setRelationshipTypes] = useState<string>("");
  const [showRebuildDialog, setShowRebuildDialog] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Does the selected collection already have a graph?
  const selectedHasGraph =
    selectedCollectionId !== "" && graphCollectionIds.has(selectedCollectionId);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // Start polling when build is in progress
  const startPolling = useCallback(
    (collectionId: string) => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(async () => {
        const progress = await pollBuildStatus(collectionId);
        if (
          progress &&
          (progress.status === "completed" || progress.status === "failed")
        ) {
          if (pollingRef.current) clearInterval(pollingRef.current);
          if (progress.status === "completed") {
            await fetchStats(collectionId);
            fetchGraphCollectionIds();
            onBuildComplete?.();
          }
        }
      }, 2000);
    },
    [pollBuildStatus, fetchStats, fetchGraphCollectionIds, onBuildComplete],
  );

  const handleStartBuild = async () => {
    if (!selectedCollectionId) return;

    // If there's already a graph, show the rebuild warning instead
    if (selectedHasGraph) {
      setShowRebuildDialog(true);
      return;
    }

    await executeBuild();
  };

  const executeBuild = async () => {
    if (!selectedCollectionId) return;

    const request = {
      collection_id: selectedCollectionId,
      entity_types: entityTypes
        ? entityTypes.split(",").map((s) => s.trim())
        : undefined,
      relationship_types: relationshipTypes
        ? relationshipTypes.split(",").map((s) => s.trim())
        : undefined,
    };

    const response = await startBuild(request);
    if (response) {
      startPolling(selectedCollectionId);
    }
  };

  const handleRebuildConfirm = async () => {
    setShowRebuildDialog(false);
    if (!selectedCollectionId) return;

    // Delete existing graph first
    await deleteGraph(selectedCollectionId);
    // Then start a fresh build
    await executeBuild();
    // Refresh graph collection IDs
    fetchGraphCollectionIds();
  };

  const handleDeleteGraph = async () => {
    if (!selectedCollectionId) return;
    await deleteGraph(selectedCollectionId);
    setBuildProgress(null);
    fetchGraphCollectionIds();
  };

  const isActive =
    buildProgress &&
    (buildProgress.status === "extracting" ||
      buildProgress.status === "building" ||
      buildProgress.status === "pending");

  const progressPercent =
    buildProgress && buildProgress.total_chunks > 0
      ? Math.round(
          (buildProgress.processed_chunks / buildProgress.total_chunks) * 100,
        )
      : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          Build Knowledge Graph
        </CardTitle>
        <CardDescription>
          Extract entities and relationships from a RAG collection and build a
          Neo4j knowledge graph.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Collection Selector */}
        <div className="space-y-2">
          <Label>Source Collection</Label>
          <Select
            value={selectedCollectionId}
            onValueChange={setSelectedCollectionId}
            disabled={!!isActive || sourcesLoading}
          >
            <SelectTrigger>
              {sourcesLoading ? (
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading sources...
                </span>
              ) : (
                <SelectValue placeholder="Select a collection..." />
              )}
            </SelectTrigger>
            <SelectContent>
              {allSources.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  <span className="flex items-center gap-2">
                    {s.name}
                    {s.isDataSource && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        data source
                      </Badge>
                    )}
                    {graphCollectionIds.has(s.id) && (
                      <Badge variant="secondary" className="text-[10px] px-1 py-0 bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        graph built
                      </Badge>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Warning for already-built collections */}
          {selectedHasGraph && !isActive && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">This collection already has a knowledge graph.</p>
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  Building again will delete all existing nodes and relationships, then create a new graph from scratch.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Optional entity/relationship type filters */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label className="text-xs">
              Entity Types{" "}
              <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              placeholder="Person, Organization, ..."
              value={entityTypes}
              onChange={(e) => setEntityTypes(e.target.value)}
              disabled={!!isActive}
              className="h-8 text-sm"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">
              Relationship Types{" "}
              <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              placeholder="WORKS_AT, KNOWS, ..."
              value={relationshipTypes}
              onChange={(e) => setRelationshipTypes(e.target.value)}
              disabled={!!isActive}
              className="h-8 text-sm"
            />
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <Button
            onClick={handleStartBuild}
            disabled={!selectedCollectionId || !!isActive}
            variant={selectedHasGraph ? "outline" : "default"}
            className="flex-1"
          >
            {isActive ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : selectedHasGraph ? (
              <RefreshCw className="mr-2 h-4 w-4" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            {isActive ? "Building..." : selectedHasGraph ? "Rebuild Graph" : "Build Graph"}
          </Button>

          {/* Rebuild confirmation dialog */}
          <AlertDialog open={showRebuildDialog} onOpenChange={setShowRebuildDialog}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Rebuild Knowledge Graph?</AlertDialogTitle>
                <AlertDialogDescription>
                  This collection already has a knowledge graph. Rebuilding will{" "}
                  <span className="font-semibold text-destructive">
                    permanently delete all existing nodes and relationships
                  </span>{" "}
                  and create a new graph from scratch. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleRebuildConfirm}
                  className="bg-destructive hover:bg-destructive/90 text-white"
                >
                  Delete &amp; Rebuild
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="destructive"
                size="icon"
                disabled={!selectedCollectionId || !!isActive}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete Knowledge Graph?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently delete all nodes and relationships in
                  this collection&apos;s graph. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDeleteGraph}
                  className="bg-destructive hover:bg-destructive/90 text-white"
                >
                  Delete Graph
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        {/* Progress */}
        {buildProgress && (
          <div className="space-y-3 rounded-lg border p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={STATUS_CONFIG[buildProgress.status].color}>
                  {STATUS_CONFIG[buildProgress.status].icon}
                </span>
                <span className="text-sm font-medium">
                  {STATUS_CONFIG[buildProgress.status].label}
                </span>
              </div>
              <Badge variant="outline">{progressPercent}%</Badge>
            </div>

            <Progress value={progressPercent} className="h-2" />

            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <div>
                Chunks: {buildProgress.processed_chunks} /{" "}
                {buildProgress.total_chunks}
              </div>
              <div>Entities: {buildProgress.extracted_entities}</div>
              <div>Relations: {buildProgress.extracted_relations}</div>
              {buildProgress.error && (
                <div className="col-span-2 text-red-500">
                  Error: {buildProgress.error}
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
