"use client";
import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

import useSWR from "swr";
import { mutate } from "swr";
import type { DocumentBoostStatus } from "@/lib/types";
import { fetchMostReactedDocuments } from "@/lib/api/domains/knowledge/api";

import { useEffect, useMemo, useRef } from "react";
import useSWRInfinite from "swr/infinite";
import type { RagCollection } from "@/lib/api/domains/knowledge/types";
import type { RagDocument } from "@/lib/api/domains/knowledge/types";
import type { RagDocumentChunksResponse } from "@/lib/api/domains/knowledge/types";
import type { GraphBuildStatusResponse } from "@/lib/api/domains/knowledge/types";
import type { UploadProgress } from "@/lib/api/domains/knowledge/types";
import type { GraphStats } from "@/lib/api/domains/knowledge/types";

import { fetchCollectionList } from "@/lib/api/domains/knowledge/api";
import { fetchCollectionDocuments } from "@/lib/api/domains/knowledge/api";
import { fetchCollectionChunks } from "@/lib/api/domains/knowledge/api";
import { fetchGraphBuildStatusForPolling } from "@/lib/api/domains/knowledge/api";
import { fetchUploadStatusForPolling } from "@/lib/api/domains/knowledge/api";
import { fetchCollectionGraphStats } from "@/lib/api/domains/knowledge/api";
import { fetchGraphCollectionList } from "@/lib/api/domains/knowledge/api";
import {
  fetchKnowledgeNeighborhood,
  fetchKnowledgeSearchSources,
  searchKnowledge,
} from "@/lib/api/domains/knowledge/api";
import {
  DEPTH_EXPANSION_LIMIT,
  type KnowledgeGraph,
  type KnowledgeNeighborhoodGroup,
  type KnowledgeSearchRequest,
  type KnowledgeSearchResponse,
  type KnowledgeSearchSource,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import { Tag } from "@/lib/types";
import { useState } from "react";
import { DateRangePickerValue } from "@/lib/api/domains/knowledge/types";
import { SourceMetadata } from "@/lib/search/interfaces";

import { fetchValidTags } from "@/lib/api/domains/knowledge/api";

import { DocumentSetSummary } from "@/lib/types";
import { fetchDocumentSets } from "@/lib/api/domains/knowledge/api";

export function useMostReactedToDocuments(ascending: boolean, limit: number) {
  const key = `${knowledgeEndpoints.updateBoost.browserPath}?ascending=${ascending}&limit=${limit}`;
  const swrResponse = useSWR<DocumentBoostStatus[]>(key, () =>
    fetchMostReactedDocuments<DocumentBoostStatus[]>(ascending, limit)
  );
  return { ...swrResponse, refreshDocs: () => mutate(key) };
}

export function useCollections() {
  const { data, error, isLoading, mutate } = useSWR<RagCollection[]>(
    knowledgeEndpoints.ragCollections.browserPath,
    () => fetchCollectionList()
  );
  return { collections: data ?? [], isLoading, error, mutate };
}

export function useDocuments(
  collectionId: string | null,
  limit = 20,
  offset = 0
) {
  const { data, error, isLoading, mutate } = useSWR<RagDocument[]>(
    collectionId
      ? knowledgeEndpoints.knowledgeDocuments(collectionId, limit, offset)
          .browserPath
      : null,
    () => fetchCollectionDocuments(collectionId!, limit, offset)
  );
  return { documents: data ?? [], isLoading, error, mutate };
}

export function useDocumentChunks(
  collectionId: string | null,
  documentId: string | null
) {
  const { data, error, isLoading, size, setSize, mutate } =
    useSWRInfinite<RagDocumentChunksResponse>(
      (pageIndex, previousPageData) => {
        if (!collectionId || !documentId) return null;
        if (previousPageData && !previousPageData.has_more) return null;
        const offset = pageIndex * 20;
        return knowledgeEndpoints.knowledgeChunks(
          collectionId,
          documentId,
          offset
        ).browserPath;
      },
      (key: string) =>
        fetchCollectionChunks(
          collectionId!,
          documentId!,
          Number(new URLSearchParams(key.split("?")[1]).get("offset"))
        )
    );

  const chunks = useMemo(
    () => data?.flatMap((page) => page.chunks) ?? [],
    [data]
  );
  const stats = data?.[0]?.stats ?? null;
  const hasMore = data ? data[data.length - 1]?.has_more ?? false : false;
  const isLoadingMore =
    isLoading ||
    (size > 0 && data !== undefined && data[size - 1] === undefined);

  return {
    chunks,
    stats,
    isLoading,
    isLoadingMore,
    hasMore,
    loadMore: () => setSize(size + 1),
    error,
    mutate,
  };
}

export function useGraphBuildStatus(
  collectionId: string | null,
  active: boolean
) {
  const { data, error, isLoading, mutate } =
    useSWR<GraphBuildStatusResponse | null>(
      active && collectionId
        ? knowledgeEndpoints.ragGraphBuildStatus(collectionId).browserPath
        : null,
      () => fetchGraphBuildStatusForPolling(collectionId!),
      { refreshInterval: 2_000 }
    );
  return { status: data ?? null, isLoading, error, mutate };
}

export function useUploadStatus(collectionId: string | null, active: boolean) {
  const { data, error, isLoading, mutate } = useSWR<UploadProgress | null>(
    active && collectionId
      ? knowledgeEndpoints.ragCollectionDocumentUploadJobsStatus(collectionId)
          .browserPath
      : null,
    () => fetchUploadStatusForPolling(collectionId!),
    { refreshInterval: 2_000 }
  );
  return { progress: data ?? null, isLoading, error, mutate };
}

export function useGraphStats(collectionId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<GraphStats>(
    collectionId
      ? knowledgeEndpoints.ragGraphCollectionStats(collectionId).browserPath
      : null,
    () => fetchCollectionGraphStats(collectionId!)
  );
  return { stats: data ?? null, isLoading, error, mutate };
}

export function useGraphCollections() {
  const { data, error, isLoading, mutate } = useSWR<string[]>(
    knowledgeEndpoints.ragGraphCollections().browserPath,
    () => fetchGraphCollectionList()
  );
  return { graphCollections: data ?? [], isLoading, error, mutate };
}

export const useTimeRange = (initialValue?: DateRangePickerValue) => {
  return useState<DateRangePickerValue | null>(null);
};

export interface FilterManager {
  timeRange: DateRangePickerValue | null;
  setTimeRange: React.Dispatch<
    React.SetStateAction<DateRangePickerValue | null>
  >;
  selectedSources: SourceMetadata[];
  setSelectedSources: React.Dispatch<React.SetStateAction<SourceMetadata[]>>;
  selectedDocumentSets: string[];
  setSelectedDocumentSets: React.Dispatch<React.SetStateAction<string[]>>;
  selectedTags: Tag[];
  setSelectedTags: React.Dispatch<React.SetStateAction<Tag[]>>;
  getFilterString: () => string;
  buildFiltersFromQueryString: (
    filterString: string,
    availableSources: SourceMetadata[],
    availableDocumentSets: string[],
    availableTags: Tag[]
  ) => void;
  clearFilters: () => void;
}

export function useFilters(): FilterManager {
  const [timeRange, setTimeRange] = useTimeRange();
  const [selectedSources, setSelectedSources] = useState<SourceMetadata[]>([]);
  const [selectedDocumentSets, setSelectedDocumentSets] = useState<string[]>(
    []
  );
  const [selectedTags, setSelectedTags] = useState<Tag[]>([]);

  function getFilterString() {
    const params = new URLSearchParams();

    if (timeRange) {
      params.set("from", timeRange.from.toISOString());
      params.set("to", timeRange.to.toISOString());
    }

    if (selectedSources.length > 0) {
      const sourcesParam = selectedSources
        .map((source) => encodeURIComponent(source.internalName))
        .join(",");
      params.set("sources", sourcesParam);
    }

    if (selectedDocumentSets.length > 0) {
      const docSetsParam = selectedDocumentSets
        .map((ds) => encodeURIComponent(ds))
        .join(",");
      params.set("documentSets", docSetsParam);
    }

    if (selectedTags.length > 0) {
      const tagsParam = selectedTags
        .map((tag) => encodeURIComponent(tag.tag_value))
        .join(",");
      params.set("tags", tagsParam);
    }

    const queryString = params.toString();
    return queryString ? `&${queryString}` : "";
  }

  function clearFilters() {
    setTimeRange(null);
    setSelectedSources([]);
    setSelectedDocumentSets([]);
    setSelectedTags([]);
  }

  function buildFiltersFromQueryString(
    filterString: string,
    availableSources: SourceMetadata[],
    availableDocumentSets: string[],
    availableTags: Tag[]
  ): void {
    const params = new URLSearchParams(filterString);

    // Parse the "from" parameter as a DateRangePickerValue
    let newTimeRange: DateRangePickerValue | null = null;
    const fromParam = params.get("from");
    const toParam = params.get("to");
    if (fromParam && toParam) {
      const fromDate = new Date(fromParam);
      const toDate = new Date(toParam);
      if (!isNaN(fromDate.getTime()) && !isNaN(toDate.getTime())) {
        newTimeRange = { from: fromDate, to: toDate, selectValue: "" };
      }
    }

    // Parse sources
    let newSelectedSources: SourceMetadata[] = [];
    const sourcesParam = params.get("sources");
    if (sourcesParam) {
      const sourceNames = sourcesParam.split(",").map(decodeURIComponent);
      newSelectedSources = availableSources.filter((source) =>
        sourceNames.includes(source.internalName)
      );
    }

    // Parse document sets
    let newSelectedDocSets: string[] = [];
    const docSetsParam = params.get("documentSets");
    if (docSetsParam) {
      const docSetNames = docSetsParam.split(",").map(decodeURIComponent);
      newSelectedDocSets = availableDocumentSets.filter((ds) =>
        docSetNames.includes(ds)
      );
    }

    // Parse tags
    let newSelectedTags: Tag[] = [];
    const tagsParam = params.get("tags");
    if (tagsParam) {
      const tagValues = tagsParam.split(",").map(decodeURIComponent);
      newSelectedTags = availableTags.filter((tag) =>
        tagValues.includes(tag.tag_value)
      );
    }

    // Update filter manager's values instead of returning
    setTimeRange(newTimeRange);
    setSelectedSources(newSelectedSources);
    setSelectedDocumentSets(newSelectedDocSets);
    setSelectedTags(newSelectedTags);
  }

  return {
    clearFilters,
    timeRange,
    setTimeRange,
    selectedSources,
    setSelectedSources,
    selectedDocumentSets,
    setSelectedDocumentSets,
    selectedTags,
    setSelectedTags,
    getFilterString,
    buildFiltersFromQueryString,
  };
}

/**
 * Fetches the set of valid tags from the server.
 *
 * Tags are deduplicated for 60 s and not re-fetched on window focus.
 *
 * @returns tags - The array of available {@link Tag} objects (empty while loading).
 * @returns isLoading - `true` until the first successful fetch or an error.
 * @returns error - The error object if the request failed.
 * @returns refresh - SWR mutate function to manually re-fetch.
 */
export function useTags() {
  const { data, error, mutate } = useSWR<Tag[]>(
    knowledgeEndpoints.validTags.browserPath,
    fetchValidTags,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  return {
    tags: data ?? [],
    isLoading: !error && !data,
    error,
    refresh: mutate,
  };
}

export function useDocumentSets() {
  const { data, error, mutate } = useSWR<DocumentSetSummary[]>(
    knowledgeEndpoints.documentSets.browserPath,
    fetchDocumentSets,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    }
  );

  return {
    documentSets: data ?? [],
    isLoading: !error && !data,
    error,
    refresh: mutate,
  };
}

// ── Knowledge search ─────────────────────────────────────────────────────────

/** Collections the knowledge search page can search. */
export function useKnowledgeSearchSources() {
  const { data, error, isLoading, mutate } = useSWR<KnowledgeSearchSource[]>(
    knowledgeEndpoints.ragSearchSources.browserPath,
    () => fetchKnowledgeSearchSources(),
    { revalidateOnFocus: false }
  );
  return { sources: data ?? [], error, isLoading, mutate };
}

/**
 * Run a knowledge search; `null` keeps the hook idle. A superseded request is
 * aborted. While a changed request loads, the previous response stays as
 * `result` only when it answers the same query (a filter or setting change);
 * a response to another query is never handed out as this query's result.
 * `isSearching` is true until the response for the current request arrives or
 * fails; a failed query leaves the error, not a pending search.
 */
export function useKnowledgeSearch(request: KnowledgeSearchRequest | null) {
  const inFlight = useRef<AbortController | null>(null);
  const { data, error, isLoading, isValidating, mutate } = useSWR<
    KnowledgeSearchResponse,
    Error,
    readonly [string, KnowledgeSearchRequest] | null
  >(
    request ? [knowledgeEndpoints.ragSearch.browserPath, request] : null,
    ([, pending]) => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      return searchKnowledge(pending, controller.signal);
    },
    {
      keepPreviousData: true,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      shouldRetryOnError: false,
    }
  );
  useEffect(() => () => inFlight.current?.abort(), []);
  const answersAnotherQuery =
    request !== null && data !== undefined && data.query !== request.query;
  return {
    result: answersAnotherQuery ? undefined : data,
    error,
    isLoading,
    isValidating,
    isSearching: isValidating || (answersAnotherQuery && !error),
    retry: mutate,
  };
}

/**
 * Expand the knowledge graph around seed nodes of several collections at
 * `depth` hops; an empty `groups` keeps the hook idle.
 */
export function useKnowledgeNeighborhoods(
  groups: readonly KnowledgeNeighborhoodGroup[],
  depth: number
) {
  const { data, error, isLoading } = useSWR<
    KnowledgeGraph[],
    Error,
    readonly [string, number, typeof groups] | null
  >(
    groups.length > 0
      ? [knowledgeEndpoints.ragSearchNeighborhood.browserPath, depth, groups]
      : null,
    ([, hops, pending]) =>
      Promise.all(
        pending.map((group) =>
          fetchKnowledgeNeighborhood({
            collectionId: group.collectionId,
            nodeIds: group.nodeIds,
            depth: hops,
            limit: DEPTH_EXPANSION_LIMIT,
          })
        )
      ),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );
  return { graphs: data ?? [], error, isLoading };
}
