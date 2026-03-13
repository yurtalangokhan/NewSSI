/**
 * React hooks for Graph RAG operations.
 * Communicates with LangConnect /graph/* API endpoints.
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { useAuthContext } from "@/providers/Auth";
import { getAccessToken } from "@/lib/auth/supabase-client";
import type {
  GraphData,
  GraphStats,
  BuildProgress,
  GraphBuildRequest,
  GraphBuildResponse,
  GraphSearchQuery,
  GraphSearchResult,
  CypherQueryRequest,
  CypherQueryResult,
  GraphNode,
  GraphEdge,
  PaginatedCounts,
  ClusteredGraphData,
  GraphViewMode,
} from "@/types/graph";

// ============================================================================
// API Helper
// ============================================================================

function getGraphApiUrl(): string {
  const url = process.env.NEXT_PUBLIC_RAG_API_URL;
  if (!url) {
    console.warn(
      "NEXT_PUBLIC_RAG_API_URL not set, falling back to http://localhost:8083",
    );
    return "http://localhost:8083";
  }
  return url;
}

function authHeaders(accessToken: string): HeadersInit {
  return {
    Authorization: `Bearer ${accessToken}`,
    "Content-Type": "application/json",
  };
}

// ============================================================================
// Graph Collection IDs Hook
// ============================================================================

/**
 * Fetches the list of collection IDs that have a knowledge graph built in Neo4j.
 * Use this to filter the global collection list to "graph-ready" collections.
 */
export function useGraphCollectionIds() {
  const { session } = useAuthContext();
  const [graphCollectionIds, setGraphCollectionIds] = useState<Set<string>>(
    new Set(),
  );
  const [loadingIds, setLoadingIds] = useState(false);

  const fetchGraphCollectionIds = useCallback(async (): Promise<Set<string>> => {
    if (!session?.accessToken) return new Set();
    setLoadingIds(true);
    try {
      const res = await fetch(`${getGraphApiUrl()}/graph/collections`, {
        headers: authHeaders(session.accessToken),
      });
      if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
      const ids: string[] = await res.json();
      const idSet = new Set(ids);
      setGraphCollectionIds(idSet);
      return idSet;
    } catch (error) {
      console.error("Failed to fetch graph collection IDs:", error);
      return new Set();
    } finally {
      setLoadingIds(false);
    }
  }, [session]);

  return { graphCollectionIds, loadingIds, fetchGraphCollectionIds };
}

// ============================================================================
// Graph Data Hook
// ============================================================================

export function useGraphData() {
  const { session } = useAuthContext();
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [scalableData, setScalableData] = useState<ClusteredGraphData | null>(null);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<GraphViewMode>("auto");

  const fetchGraphData = useCallback(
    async (
      collectionId: string,
      nodeLimit = 200,
      edgeLimit = 500,
    ): Promise<GraphData | null> => {
      if (!session?.accessToken) return null;
      // Background fetch for entity preview — does NOT touch the shared loading
      // state so it won't prematurely dismiss the loading skeleton.
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/data?node_limit=${nodeLimit}&edge_limit=${edgeLimit}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: GraphData = await res.json();
        setGraphData(data);
        return data;
      } catch (error) {
        console.error("Failed to fetch graph data:", error);
        toast.error("Failed to load graph data");
        return null;
      }
    },
    [session],
  );

  const fetchStats = useCallback(
    async (
      collectionId: string,
      scopeLabel?: string,
    ): Promise<GraphStats | null> => {
      if (!session?.accessToken) return null;
      try {
        let url = `${getGraphApiUrl()}/graph/collections/${collectionId}/stats`;
        if (scopeLabel) {
          url += `?scope_label=${encodeURIComponent(scopeLabel)}`;
        }
        const res = await fetch(url, {
          headers: authHeaders(session.accessToken),
        });
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: GraphStats = await res.json();
        setStats(data);
        return data;
      } catch (error) {
        console.error("Failed to fetch graph stats:", error);
        return null;
      }
    },
    [session],
  );

  const fetchNodes = useCallback(
    async (
      collectionId: string,
      limit = 100,
      offset = 0,
      label?: string,
    ): Promise<GraphNode[]> => {
      if (!session?.accessToken) return [];
      try {
        let url = `${getGraphApiUrl()}/graph/collections/${collectionId}/nodes?limit=${limit}&offset=${offset}`;
        if (label) url += `&label=${encodeURIComponent(label)}`;
        const res = await fetch(url, {
          headers: authHeaders(session.accessToken),
        });
        if (!res.ok) return [];
        return await res.json();
      } catch {
        return [];
      }
    },
    [session],
  );

  const fetchEdges = useCallback(
    async (
      collectionId: string,
      limit = 200,
      offset = 0,
    ): Promise<GraphEdge[]> => {
      if (!session?.accessToken) return [];
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/edges?limit=${limit}&offset=${offset}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) return [];
        return await res.json();
      } catch {
        return [];
      }
    },
    [session],
  );

  const deleteGraph = useCallback(
    async (collectionId: string): Promise<boolean> => {
      if (!session?.accessToken) return false;
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}`,
          {
            method: "DELETE",
            headers: authHeaders(session.accessToken),
          },
        );
        if (res.ok || res.status === 204) {
          setGraphData(null);
          setStats(null);
          toast.success("Graph deleted successfully");
          return true;
        }
        throw new Error(`Failed: ${res.statusText}`);
      } catch (error) {
        console.error("Failed to delete graph:", error);
        toast.error("Failed to delete graph");
        return false;
      }
    },
    [session],
  );

  const fetchLabelsPaginated = useCallback(
    async (
      collectionId: string,
      page = 1,
      pageSize = 25,
      search?: string,
      scopeLabel?: string,
      relTypeFilter?: string[],
    ): Promise<PaginatedCounts | null> => {
      if (!session?.accessToken) return null;
      try {
        let url = `${getGraphApiUrl()}/graph/collections/${collectionId}/stats/labels?page=${page}&page_size=${pageSize}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (scopeLabel) url += `&scope_label=${encodeURIComponent(scopeLabel)}`;
        if (relTypeFilter?.length)
          url += `&rel_type_filter=${encodeURIComponent(relTypeFilter.join(","))}`;
        const res = await fetch(url, {
          headers: authHeaders(session.accessToken),
        });
        if (!res.ok) return null;
        return await res.json();
      } catch {
        return null;
      }
    },
    [session],
  );

  const fetchRelTypesPaginated = useCallback(
    async (
      collectionId: string,
      page = 1,
      pageSize = 25,
      search?: string,
      scopeLabel?: string,
      labelFilter?: string[],
    ): Promise<PaginatedCounts | null> => {
      if (!session?.accessToken) return null;
      try {
        let url = `${getGraphApiUrl()}/graph/collections/${collectionId}/stats/relationship-types?page=${page}&page_size=${pageSize}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (scopeLabel) url += `&scope_label=${encodeURIComponent(scopeLabel)}`;
        if (labelFilter?.length)
          url += `&label_filter=${encodeURIComponent(labelFilter.join(","))}`;
        const res = await fetch(url, {
          headers: authHeaders(session.accessToken),
        });
        if (!res.ok) return null;
        return await res.json();
      } catch {
        return null;
      }
    },
    [session],
  );

  // ---- Scalable Graph Data ----

  const fetchScalableGraphData = useCallback(
    async (
      collectionId: string,
      mode: GraphViewMode = "auto",
      nodeLimit = 500,
      edgeLimit = 1000,
    ): Promise<ClusteredGraphData | null> => {
      if (!session?.accessToken) return null;
      setLoading(true);
      try {
        const params = new URLSearchParams({
          mode,
          node_limit: String(nodeLimit),
          edge_limit: String(edgeLimit),
        });
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/data/scalable?${params}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: ClusteredGraphData = await res.json();
        setScalableData(data);
        setViewMode(data.mode as GraphViewMode);
        // Re-fetch stats: scoped if expand, global otherwise
        const statsScope = data.scope_label
          ? `?scope_label=${encodeURIComponent(data.scope_label)}`
          : "";
        fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/stats${statsScope}`,
          { headers: authHeaders(session.accessToken) },
        )
          .then((r) => (r.ok ? r.json() : null))
          .then((s) => { if (s) setStats(s); })
          .catch(() => {});
        return data;
      } catch (error) {
        console.error("Failed to fetch scalable graph data:", error);
        toast.error("Failed to load scalable graph data");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  const fetchNeighborhood = useCallback(
    async (
      collectionId: string,
      nodeId: string,
      depth = 1,
      limit = 50,
    ): Promise<GraphData | null> => {
      if (!session?.accessToken) return null;
      setScalableData(null); // clear stale data immediately
      setLoading(true);
      try {
        const params = new URLSearchParams({
          node_id: nodeId,
          depth: String(depth),
          limit: String(limit),
        });
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/neighborhood?${params}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: GraphData = await res.json();
        setGraphData(data);
        // Also update scalableData so activeData picks up the neighborhood view
        setScalableData({
          nodes: data.nodes,
          edges: data.edges,
          total_node_count: data.nodes.length,
          total_edge_count: data.edges.length,
          cluster_count: 0,
          mode: "neighborhood",
        });
        setViewMode("neighborhood");
        // Re-fetch global stats for neighborhood view
        fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/stats`,
          { headers: authHeaders(session.accessToken) },
        )
          .then((r) => (r.ok ? r.json() : null))
          .then((s) => { if (s) setStats(s); })
          .catch(() => {});
        return data;
      } catch (error) {
        console.error("Failed to fetch neighborhood:", error);
        toast.error("Failed to load neighborhood");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  const expandCluster = useCallback(
    async (
      collectionId: string,
      label: string,
      nodeLimit = 200,
      edgeLimit = 500,
    ): Promise<ClusteredGraphData | null> => {
      if (!session?.accessToken) return null;
      setLoading(true);
      try {
        // Use the scalable endpoint with mode=expand so the backend can
        // sub-cluster when the label group is too large.
        const params = new URLSearchParams({
          mode: "expand",
          cluster_label: label,
          node_limit: String(nodeLimit),
          edge_limit: String(edgeLimit),
        });
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/data/scalable?${params}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: ClusteredGraphData = await res.json();
        setScalableData(data);
        setViewMode("expand");
        // Re-fetch stats scoped to the expanded label so counts/labels match
        if (data.scope_label) {
          const statsUrl = `${getGraphApiUrl()}/graph/collections/${collectionId}/stats?scope_label=${encodeURIComponent(data.scope_label)}`;
          fetch(statsUrl, { headers: authHeaders(session.accessToken) })
            .then((r) => (r.ok ? r.json() : null))
            .then((s) => { if (s) setStats(s); })
            .catch(() => {});
        }
        return data;
      } catch (error) {
        console.error("Failed to expand cluster:", error);
        toast.error("Failed to expand cluster");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  return {
    graphData,
    scalableData,
    stats,
    loading,
    viewMode,
    setViewMode,
    fetchGraphData,
    fetchScalableGraphData,
    fetchNeighborhood,
    expandCluster,
    fetchStats,
    fetchNodes,
    fetchEdges,
    deleteGraph,
    fetchLabelsPaginated,
    fetchRelTypesPaginated,
  };
}

// ============================================================================
// Build Pipeline Hook
// ============================================================================

export function useGraphBuild() {
  const { session } = useAuthContext();
  const [buildProgress, setBuildProgress] = useState<BuildProgress | null>(
    null,
  );
  const [isBuilding, setIsBuilding] = useState(false);

  const startBuild = useCallback(
    async (request: GraphBuildRequest): Promise<GraphBuildResponse | null> => {
      if (!session?.accessToken) return null;
      setIsBuilding(true);
      try {
        const res = await fetch(`${getGraphApiUrl()}/graph/build`, {
          method: "POST",
          headers: authHeaders(session.accessToken),
          body: JSON.stringify(request),
        });
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: GraphBuildResponse = await res.json();
        toast.success(data.message);
        return data;
      } catch (error) {
        console.error("Failed to start build:", error);
        toast.error("Failed to start graph build");
        return null;
      } finally {
        setIsBuilding(false);
      }
    },
    [session],
  );

  const pollBuildStatus = useCallback(
    async (collectionId: string): Promise<BuildProgress | null> => {
      // Always fetch a fresh token via Supabase's getSession() which
      // auto-refreshes expired JWTs.  This avoids the stale-closure
      // problem where a long-running polling loop holds an expired token.
      const token = await getAccessToken();
      if (!token) return null;
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/build/${collectionId}/status`,
          { headers: authHeaders(token) },
        );
        if (!res.ok) return null;
        // Backend returns null (JSON null) when no build has ever
        // been started for this collection.
        const text = await res.text();
        if (!text || text === "null") return null;
        const data: BuildProgress = JSON.parse(text);
        setBuildProgress(data);
        return data;
      } catch {
        return null;
      }
    },
    [],
  );

  return {
    buildProgress,
    isBuilding,
    startBuild,
    pollBuildStatus,
    setBuildProgress,
  };
}

// ============================================================================
// Search Hook
// ============================================================================

export function useGraphSearch() {
  const { session } = useAuthContext();
  const [searchResults, setSearchResults] = useState<GraphSearchResult | null>(
    null,
  );
  const [searching, setSearching] = useState(false);

  const search = useCallback(
    async (query: GraphSearchQuery): Promise<GraphSearchResult | null> => {
      if (!session?.accessToken) return null;
      setSearching(true);
      try {
        const res = await fetch(`${getGraphApiUrl()}/graph/search`, {
          method: "POST",
          headers: authHeaders(session.accessToken),
          body: JSON.stringify(query),
        });
        if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
        const data: GraphSearchResult = await res.json();
        setSearchResults(data);
        return data;
      } catch (error) {
        console.error("Graph search failed:", error);
        toast.error("Graph search failed");
        return null;
      } finally {
        setSearching(false);
      }
    },
    [session],
  );

  const searchEntities = useCallback(
    async (collectionId: string, q: string, limit = 10) => {
      if (!session?.accessToken) return null;
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/search/entities?q=${encodeURIComponent(q)}&limit=${limit}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) return null;
        return await res.json();
      } catch {
        return null;
      }
    },
    [session],
  );

  const executeCypher = useCallback(
    async (
      request: CypherQueryRequest,
    ): Promise<CypherQueryResult | null> => {
      if (!session?.accessToken) return null;
      try {
        const res = await fetch(`${getGraphApiUrl()}/graph/cypher`, {
          method: "POST",
          headers: authHeaders(session.accessToken),
          body: JSON.stringify(request),
        });
        if (!res.ok) {
          const err = await res.json();
          toast.error(err.detail || "Cypher query failed");
          return null;
        }
        return await res.json();
      } catch (error) {
        console.error("Cypher query failed:", error);
        toast.error("Cypher query failed");
        return null;
      }
    },
    [session],
  );

  const searchEntityClusters = useCallback(
    async (
      collectionId: string,
      q: string,
    ): Promise<Record<string, number> | null> => {
      if (!session?.accessToken) return null;
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/search/entity-clusters?q=${encodeURIComponent(q)}`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) return null;
        return await res.json();
      } catch {
        return null;
      }
    },
    [session],
  );

  return {
    searchResults,
    searching,
    search,
    searchEntities,
    searchEntityClusters,
    executeCypher,
    setSearchResults,
  };
}
