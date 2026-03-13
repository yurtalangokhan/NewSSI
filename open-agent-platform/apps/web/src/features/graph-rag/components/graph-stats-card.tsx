/**
 * Graph statistics card – shows node/edge counts and paginated, searchable
 * label & relationship-type breakdowns.
 * Labels and relationship types are clickable multi-select filters.
 *
 * ALL search and pagination is handled server-side via the paginated API.
 * When `scopeLabel` is provided the backend scopes results to the
 * neighbour labels / relationship types of that label group.
 *
 * **Cross-filtering**: selecting relationship types re-fetches labels
 * (only labels of nodes participating in those rel types) and vice-versa.
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
  /** Override node count with actual visible data count (deep expand). */
  visibleNodeCount?: number;
  /** Override edge count with actual visible data count (deep expand). */
  visibleEdgeCount?: number;
  /** Paginated fetcher for entity labels */
  fetchLabelsPaginated?: (
    collectionId: string,
    page: number,
    pageSize: number,
    search?: string,
    scopeLabel?: string,
    relTypeFilter?: string[],
  ) => Promise<PaginatedCounts | null>;
  /** Paginated fetcher for relationship types */
  fetchRelTypesPaginated?: (
    collectionId: string,
    page: number,
    pageSize: number,
    search?: string,
    scopeLabel?: string,
    labelFilter?: string[],
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
  visibleNodeCount,
  visibleEdgeCount,
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

  // ── Cross-filter arrays (stable via serialised key) ───────────────
  const relTypeFilterArr = useMemo(
    () =>
      selectedRelTypes && selectedRelTypes.size > 0
        ? Array.from(selectedRelTypes).sort()
        : undefined,
    [selectedRelTypes],
  );
  const labelFilterArr = useMemo(
    () =>
      selectedLabels && selectedLabels.size > 0
        ? Array.from(selectedLabels).sort()
        : undefined,
    [selectedLabels],
  );
  // Serialised keys for effect dependencies (Set is not stable)
  const relTypeFilterKey = relTypeFilterArr?.join(",") ?? "";
  const labelFilterKey = labelFilterArr?.join(",") ?? "";

  // ── Fetch labels ──────────────────────────────────────────────────
  const loadLabels = useCallback(
    async (page: number, search: string, scope?: string, relTypeFilter?: string[]) => {
      if (!collectionId || !fetchLabelsPaginated) return;
      setLabelsLoading(true);
      const data = await fetchLabelsPaginated(
        collectionId,
        page,
        PAGE_SIZE,
        search || undefined,
        scope || undefined,
        relTypeFilter,
      );
      setLabelsData(data);
      setLabelsLoading(false);
    },
    [collectionId, fetchLabelsPaginated],
  );

  // ── Fetch rel types ───────────────────────────────────────────────
  const loadRelTypes = useCallback(
    async (page: number, search: string, scope?: string, labelFilter?: string[]) => {
      if (!collectionId || !fetchRelTypesPaginated) return;
      setRelLoading(true);
      const data = await fetchRelTypesPaginated(
        collectionId,
        page,
        PAGE_SIZE,
        search || undefined,
        scope || undefined,
        labelFilter,
      );
      setRelData(data);
      setRelLoading(false);
    },
    [collectionId, fetchRelTypesPaginated],
  );

  // ── Reload labels when collection, scope, or rel-type filter changes
  useEffect(() => {
    if (!hasPaginatedApi) return;
    setLabelsPage(1);
    setLabelsSearch("");
    loadLabels(1, "", scopeLabel, relTypeFilterArr);
    return () => clearTimeout(labelsDebounce.current);
  }, [collectionId, scopeLabel, hasPaginatedApi, relTypeFilterKey]);

  // ── Reload rel-types when collection, scope, or label filter changes
  useEffect(() => {
    if (!hasPaginatedApi) return;
    setRelPage(1);
    setRelSearch("");
    loadRelTypes(1, "", scopeLabel, labelFilterArr);
    return () => clearTimeout(relDebounce.current);
  }, [collectionId, scopeLabel, hasPaginatedApi, labelFilterKey]);

  // ── Page navigation handlers ──────────────────────────────────────
  const goToLabelsPage = useCallback(
    (page: number) => {
      setLabelsPage(page);
      loadLabels(page, labelsSearch, scopeLabel, relTypeFilterArr);
    },
    [loadLabels, labelsSearch, scopeLabel, relTypeFilterArr],
  );

  const goToRelPage = useCallback(
    (page: number) => {
      setRelPage(page);
      loadRelTypes(page, relSearch, scopeLabel, labelFilterArr);
    },
    [loadRelTypes, relSearch, scopeLabel, labelFilterArr],
  );

  // ── Debounced search handlers ─────────────────────────────────────
  const handleLabelsSearchChange = useCallback(
    (value: string) => {
      setLabelsSearch(value);
      clearTimeout(labelsDebounce.current);
      labelsDebounce.current = setTimeout(() => {
        setLabelsPage(1);
        loadLabels(1, value, scopeLabel, relTypeFilterArr);
      }, 300);
    },
    [loadLabels, scopeLabel, relTypeFilterArr],
  );

  const handleRelSearchChange = useCallback(
    (value: string) => {
      setRelSearch(value);
      clearTimeout(relDebounce.current);
      relDebounce.current = setTimeout(() => {
        setRelPage(1);
        loadRelTypes(1, value, scopeLabel, labelFilterArr);
      }, 300);
    },
    [loadRelTypes, scopeLabel, labelFilterArr],
  );

  // ── Data source: always from paginated backend API ────────────────
  const labelItems = labelsData?.items ?? [];
  const relItems = relData?.items ?? [];

  // Show server-side paginated controls when using the paginated API
  const showLabelsPagination = hasPaginatedApi;
  const showRelsPagination = hasPaginatedApi;

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
              <p className="text-2xl font-bold">
                {(visibleNodeCount ?? stats.node_count).toLocaleString()}
              </p>
              <p className="text-muted-foreground text-xs">
                Nodes{hasLabelFilter ? ` (${selectedLabels!.size} label filter)` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <GitBranch className="text-primary h-4 w-4" />
            <div>
              <p className="text-2xl font-bold">
                {(visibleEdgeCount ?? stats.edge_count).toLocaleString()}
              </p>
              <p className="text-muted-foreground text-xs">
                Edges{hasRelFilter ? ` (${selectedRelTypes!.size} type filter)` : ""}
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
                  onChange={(e) => handleLabelsSearchChange(e.target.value)}
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
                    onClick={() => goToLabelsPage(Math.max(1, labelsPage - 1))}
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
                    onClick={() => goToLabelsPage(labelsPage + 1)}
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
                  onChange={(e) => handleRelSearchChange(e.target.value)}
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
                    onClick={() => goToRelPage(Math.max(1, relPage - 1))}
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
                    onClick={() => goToRelPage(relPage + 1)}
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
