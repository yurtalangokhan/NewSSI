/**
 * React hooks for Graph RAG operations.
 * Communicates with LangConnect /graph/* API endpoints.
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { useAuthContext } from "@/providers/Auth";
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
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchGraphData = useCallback(
    async (
      collectionId: string,
      nodeLimit = 200,
      edgeLimit = 500,
    ): Promise<GraphData | null> => {
      if (!session?.accessToken) return null;
      setLoading(true);
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
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  const fetchStats = useCallback(
    async (collectionId: string): Promise<GraphStats | null> => {
      if (!session?.accessToken) return null;
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/collections/${collectionId}/stats`,
          { headers: authHeaders(session.accessToken) },
        );
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
    ): Promise<PaginatedCounts | null> => {
      if (!session?.accessToken) return null;
      try {
        let url = `${getGraphApiUrl()}/graph/collections/${collectionId}/stats/labels?page=${page}&page_size=${pageSize}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
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
    ): Promise<PaginatedCounts | null> => {
      if (!session?.accessToken) return null;
      try {
        let url = `${getGraphApiUrl()}/graph/collections/${collectionId}/stats/relationship-types?page=${page}&page_size=${pageSize}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
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

  return {
    graphData,
    stats,
    loading,
    fetchGraphData,
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
      if (!session?.accessToken) return null;
      try {
        const res = await fetch(
          `${getGraphApiUrl()}/graph/build/${collectionId}/status`,
          { headers: authHeaders(session.accessToken) },
        );
        if (!res.ok) return null;
        const data: BuildProgress = await res.json();
        setBuildProgress(data);
        return data;
      } catch {
        return null;
      }
    },
    [session],
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

  return {
    searchResults,
    searching,
    search,
    searchEntities,
    executeCypher,
    setSearchResults,
  };
}
