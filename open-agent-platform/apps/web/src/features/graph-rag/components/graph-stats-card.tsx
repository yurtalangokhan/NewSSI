/**
 * Graph statistics card – shows node/edge counts and paginated, searchable
 * label & relationship-type breakdowns.
 * Labels and relationship types are clickable multi-select filters.
 *
 * ALL search and pagination is handled server-side via the paginated API.
 * When `scopeLabel` is provided the backend scopes results to the
 * neighbour labels / relationship types of that label group.
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChevronLeft,
  ChevronRight,
  CircleDot,
  GitBranch,
  Search,
  Tags,
  Waypoints,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphStats, PaginatedCounts } from "@/types/graph";

interface GraphStatsCardProps {
  stats: GraphStats | null;
  loading?: boolean;
  collectionId?: string;
  /** Currently selected label filters (multi-select) */
  selectedLabels?: Set<string>;
  /** Currently selected relationship type filters (multi-select) */
  selectedRelTypes?: Set<string>;
  onToggleLabel?: (label: string) => void;
  onToggleRelType?: (relType: string) => void;
  /** Scope labels & rel-types to this label group (expand / sub-cluster). */
  scopeLabel?: string;
  /** Paginated fetcher for entity labels */
  fetchLabelsPaginated?: (
    collectionId: string,
    page: number,
    pageSize: number,
    search?: string,
    scopeLabel?: string,
  ) => Promise<PaginatedCounts | null>;
  /** Paginated fetcher for relationship types */
  fetchRelTypesPaginated?: (
    collectionId: string,
    page: number,
    pageSize: number,
    search?: string,
    scopeLabel?: string,
  ) => Promise<PaginatedCounts | null>;
}

const PAGE_SIZE = 25;

export function GraphStatsCard({
  stats,
  loading,
  collectionId,
  selectedLabels,
  selectedRelTypes,
  onToggleLabel,
  onToggleRelType,
  scopeLabel,
  fetchLabelsPaginated,
  fetchRelTypesPaginated,
}: GraphStatsCardProps) {
  // ── Pagination state for labels ───────────────────────────────────
  const [labelsData, setLabelsData] = useState<PaginatedCounts | null>(null);
  const [labelsPage, setLabelsPage] = useState(1);
  const [labelsSearch, setLabelsSearch] = useState("");
  const [labelsLoading, setLabelsLoading] = useState(false);
  const labelsDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // ── Pagination state for relationship types ───────────────────────
  const [relData, setRelData] = useState<PaginatedCounts | null>(null);
  const [relPage, setRelPage] = useState(1);
  const [relSearch, setRelSearch] = useState("");
  const [relLoading, setRelLoading] = useState(false);
  const relDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Whether we can use the paginated endpoints
  const hasPaginatedApi = !!(
    collectionId &&
    fetchLabelsPaginated &&
    fetchRelTypesPaginated
  );

  // ── Fetch labels ──────────────────────────────────────────────────
  const loadLabels = useCallback(
    async (page: number, search: string, scope?: string) => {
      if (!collectionId || !fetchLabelsPaginated) return;
      setLabelsLoading(true);
      const data = await fetchLabelsPaginated(
        collectionId,
        page,
        PAGE_SIZE,
        search || undefined,
        scope || undefined,
      );
      setLabelsData(data);
      setLabelsLoading(false);
    },
    [collectionId, fetchLabelsPaginated],
  );

  // ── Fetch rel types ───────────────────────────────────────────────
  const loadRelTypes = useCallback(
    async (page: number, search: string, scope?: string) => {
      if (!collectionId || !fetchRelTypesPaginated) return;
      setRelLoading(true);
      const data = await fetchRelTypesPaginated(
        collectionId,
        page,
        PAGE_SIZE,
        search || undefined,
        scope || undefined,
      );
      setRelData(data);
      setRelLoading(false);
    },
    [collectionId, fetchRelTypesPaginated],
  );

  // ── Reset and reload when collection or scope changes ─────────────
  useEffect(() => {
    if (!hasPaginatedApi) return;
    setLabelsPage(1);
    setLabelsSearch("");
    setRelPage(1);
    setRelSearch("");
    loadLabels(1, "", scopeLabel);
    loadRelTypes(1, "", scopeLabel);
  }, [collectionId, scopeLabel, hasPaginatedApi]);

  // ── Re-fetch labels on page change ────────────────────────────────
  useEffect(() => {
    if (!hasPaginatedApi) return;
    loadLabels(labelsPage, labelsSearch, scopeLabel);
  }, [labelsPage]);

  // ── Debounced search for labels ───────────────────────────────────
  useEffect(() => {
    if (!hasPaginatedApi) return;
    clearTimeout(labelsDebounce.current);
    labelsDebounce.current = setTimeout(() => {
      setLabelsPage(1);
      loadLabels(1, labelsSearch, scopeLabel);
    }, 300);
    return () => clearTimeout(labelsDebounce.current);
  }, [labelsSearch]);

  // ── Re-fetch rel types on page change ─────────────────────────────
  useEffect(() => {
    if (!hasPaginatedApi) return;
    loadRelTypes(relPage, relSearch, scopeLabel);
  }, [relPage]);

  // ── Debounced search for rel types ────────────────────────────────
  useEffect(() => {
    if (!hasPaginatedApi) return;
    clearTimeout(relDebounce.current);
    relDebounce.current = setTimeout(() => {
      setRelPage(1);
      loadRelTypes(1, relSearch, scopeLabel);
    }, 300);
    return () => clearTimeout(relDebounce.current);
  }, [relSearch]);

  // ── Data source: paginated API or flat stats fallback ─────────────
  const labelItems =
    hasPaginatedApi && stats
      ? (labelsData?.items ?? [])
      : stats
        ? Object.entries(stats.label_counts).map(([name, count]) => ({
            name,
            count,
          }))
        : [];
  const relItems =
    hasPaginatedApi && stats
      ? (relData?.items ?? [])
      : stats
        ? Object.entries(stats.relationship_type_counts).map(([name, count]) => ({
            name,
            count,
          }))
        : [];

  // Show server-side paginated controls when using the paginated API
  const showLabelsPagination = hasPaginatedApi;
  const showRelsPagination = hasPaginatedApi;

  // ── Filtered counts (for header) ─────────────────────────────────
  const filteredNodeCount = useMemo(() => {
    if (!stats) return 0;
    if (!selectedLabels || selectedLabels.size === 0) return stats.node_count;
    return Object.entries(stats.label_counts)
      .filter(([label]) => selectedLabels.has(label))
      .reduce((sum, [, count]) => sum + count, 0);
  }, [stats, selectedLabels]);

  const filteredEdgeCount = useMemo(() => {
    if (!stats) return 0;
    if (!selectedRelTypes || selectedRelTypes.size === 0)
      return stats.edge_count;
    return Object.entries(stats.relationship_type_counts)
      .filter(([type]) => selectedRelTypes.has(type))
      .reduce((sum, [, count]) => sum + count, 0);
  }, [stats, selectedRelTypes]);

  // ── Loading skeleton ──────────────────────────────────────────────
  if (loading) {
    return (
      <Card className="w-full">
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-3/4" />
        </CardContent>
      </Card>
    );
  }

  if (!stats) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Graph Statistics
          </CardTitle>
          <CardDescription>
            No graph data available. Build a knowledge graph first.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const hasLabelFilter = selectedLabels && selectedLabels.size > 0;
  const hasRelFilter = selectedRelTypes && selectedRelTypes.size > 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Graph Statistics</CardTitle>
        {scopeLabel && (
          <CardDescription className="text-xs">
            Scoped to <span className="font-medium">{scopeLabel}</span>
          </CardDescription>
        )}
        {(hasLabelFilter || hasRelFilter) && (
          <CardDescription className="text-xs">
            Filtering active — click badges to toggle
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* ── Counts ────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <CircleDot className="text-primary h-4 w-4" />
            <div>
              <p className="text-2xl font-bold">{filteredNodeCount}</p>
              <p className="text-muted-foreground text-xs">
                Nodes{hasLabelFilter ? " (filtered)" : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <GitBranch className="text-primary h-4 w-4" />
            <div>
              <p className="text-2xl font-bold">{filteredEdgeCount}</p>
              <p className="text-muted-foreground text-xs">
                Edges{hasRelFilter ? " (filtered)" : ""}
              </p>
            </div>
          </div>
        </div>

        {/* ── Entity Labels ─────────────────────────────── */}
        {(labelItems.length > 0 || showLabelsPagination) && (
          <div>
            <div className="mb-2 flex items-center gap-1">
              <Tags className="h-3 w-3" />
              <span className="text-xs font-medium">Entity Labels</span>
              {showLabelsPagination && labelsData && (
                <span className="text-muted-foreground ml-auto text-[10px]">
                  {labelsData.total} total
                </span>
              )}
            </div>

            {/* Search input */}
            {showLabelsPagination && (
              <div className="relative mb-2">
                <Search className="text-muted-foreground absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2" />
                <Input
                  placeholder="Search labels..."
                  value={labelsSearch}
                  onChange={(e) => setLabelsSearch(e.target.value)}
                  className="h-7 pl-7 text-xs"
                />
              </div>
            )}

            {/* Badge list */}
            <div className="flex flex-wrap gap-1">
              {labelsLoading ? (
                <>
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-5 w-16" />
                  <Skeleton className="h-5 w-24" />
                </>
              ) : (
                labelItems.map((item) => {
                  const isActive = selectedLabels?.has(item.name);
                  return (
                    <Badge
                      key={item.name}
                      variant={isActive ? "default" : "secondary"}
                      className={cn(
                        "cursor-pointer select-none text-xs transition-colors",
                        isActive && "ring-primary/30 ring-2",
                      )}
                      onClick={() => onToggleLabel?.(item.name)}
                    >
                      {item.name}: {item.count}
                    </Badge>
                  );
                })
              )}
            </div>

            {/* Pagination controls */}
            {showLabelsPagination &&
              labelsData &&
              labelsData.total > PAGE_SIZE && (
                <div className="mt-2 flex items-center justify-between">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    disabled={labelsPage <= 1}
                    onClick={() => setLabelsPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="mr-1 h-3 w-3" />
                    Prev
                  </Button>
                  <span className="text-muted-foreground text-[10px]">
                    {labelsPage} / {Math.ceil(labelsData.total / PAGE_SIZE)}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    disabled={!labelsData.has_next}
                    onClick={() => setLabelsPage((p) => p + 1)}
                  >
                    Next
                    <ChevronRight className="ml-1 h-3 w-3" />
                  </Button>
                </div>
              )}
          </div>
        )}

        {/* ── Relationship Types ────────────────────────── */}
        {(relItems.length > 0 || showRelsPagination) && (
          <div>
            <div className="mb-2 flex items-center gap-1">
              <Waypoints className="h-3 w-3" />
              <span className="text-xs font-medium">Relationship Types</span>
              {showRelsPagination && relData && (
                <span className="text-muted-foreground ml-auto text-[10px]">
                  {relData.total} total
                </span>
              )}
            </div>

            {/* Search input */}
            {showRelsPagination && (
              <div className="relative mb-2">
                <Search className="text-muted-foreground absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2" />
                <Input
                  placeholder="Search relationship types..."
                  value={relSearch}
                  onChange={(e) => setRelSearch(e.target.value)}
                  className="h-7 pl-7 text-xs"
                />
              </div>
            )}

            {/* Badge list */}
            <div className="flex flex-wrap gap-1">
              {relLoading ? (
                <>
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-5 w-16" />
                  <Skeleton className="h-5 w-24" />
                </>
              ) : (
                relItems.map((item) => {
                  const isActive = selectedRelTypes?.has(item.name);
                  return (
                    <Badge
                      key={item.name}
                      variant={isActive ? "default" : "outline"}
                      className={cn(
                        "cursor-pointer select-none text-xs transition-colors",
                        isActive && "ring-primary/30 ring-2",
                      )}
                      onClick={() => onToggleRelType?.(item.name)}
                    >
                      {item.name}: {item.count}
                    </Badge>
                  );
                })
              )}
            </div>

            {/* Pagination controls */}
            {showRelsPagination &&
              relData &&
              relData.total > PAGE_SIZE && (
                <div className="mt-2 flex items-center justify-between">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    disabled={relPage <= 1}
                    onClick={() => setRelPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="mr-1 h-3 w-3" />
                    Prev
                  </Button>
                  <span className="text-muted-foreground text-[10px]">
                    {relPage} / {Math.ceil(relData.total / PAGE_SIZE)}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    disabled={!relData.has_next}
                    onClick={() => setRelPage((p) => p + 1)}
                  >
                    Next
                    <ChevronRight className="ml-1 h-3 w-3" />
                  </Button>
                </div>
              )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
