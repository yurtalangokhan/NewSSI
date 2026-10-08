"use client";

import { useCallback, useEffect, useState, useRef, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";

// Any type that has an id property
type PaginatedType = {
  id: number | string;
  [key: string]: any;
};

export interface PaginatedApiResponse<T extends PaginatedType> {
  items: T[];
  total_items: number;
  // A filtered page reports how far the backend read, plus one probe row, so
  // that another page can be offered without counting the whole directory.
  // Absent means the endpoint always counts, as it did before.
  total_items_exact?: boolean;
}

interface PaginationConfig<T extends PaginatedType> {
  itemsPerPage: number;
  pagesPerBatch: number;
  requestKey: string;
  loadPage: (params: URLSearchParams) => Promise<PaginatedApiResponse<T>>;
  query?: string;
  filter?: Record<string, string | boolean | number | string[] | Date>;
  refreshIntervalInMs?: number; // 0 or undefined to disable polling
}

interface PaginatedHookReturnData<T extends PaginatedType> {
  currentPageData: T[] | null;
  isLoading: boolean;
  error: Error | null;
  currentPage: number;
  totalPages: number;
  totalItems: number;
  // False when totalItems is a lower bound rather than a count: enough to page
  // with, never enough to display as a total.
  totalItemsExact: boolean;
  goToPage: (page: number) => void;
  refresh: () => Promise<void>;
  updateItem: (itemId: T["id"], updater: (item: T) => T) => void;
}

function usePaginatedFetch<T extends PaginatedType>({
  itemsPerPage,
  pagesPerBatch,
  requestKey,
  loadPage,
  query,
  filter,
  refreshIntervalInMs = 0, // Disabled by default; set to > 0 to enable periodic polling
}: PaginationConfig<T>): PaginatedHookReturnData<T> {
  const router = useRouter();
  const currentPath = usePathname();
  const searchParams = useSearchParams();

  // State to initialize and hold the current page number
  const [currentPage, setCurrentPage] = useState(() =>
    parseInt(searchParams?.get("page") || "1", 10)
  );
  const [currentPageData, setCurrentPageData] = useState<T[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [totalItems, setTotalItems] = useState<number>(0);
  const [totalItemsExact, setTotalItemsExact] = useState<boolean>(true);
  const [cachedBatches, setCachedBatches] = useState<{ [key: number]: T[][] }>(
    {}
  );

  // Tracks ongoing requests to avoid duplicate requests, uses ref to persist across renders.
  // Keyed by the request's parameters as well as its batch, so that changing the
  // search term or the filters is never mistaken for a duplicate of the request
  // already in flight for the previous ones.
  const ongoingRequestsRef = useRef<Set<string>>(new Set());
  const loadPageRef = useRef(loadPage);
  useEffect(() => {
    loadPageRef.current = loadPage;
  }, [loadPage]);

  // Identifies the set of results currently being asked for. Responses that
  // belong to an earlier one are discarded instead of being cached under the
  // current search term.
  const effectiveRequestKey = useMemo(
    () =>
      JSON.stringify({
        requestKey,
        query: query ?? "",
        filter: filter ?? null,
      }),
    [requestKey, query, filter]
  );
  const requestKeyRef = useRef(effectiveRequestKey);
  requestKeyRef.current = effectiveRequestKey;

  const totalPages = useMemo(() => {
    if (totalItems === 0) return 1;
    return Math.ceil(totalItems / itemsPerPage);
  }, [totalItems, itemsPerPage]);

  // Calculates which batch we're in, and which page within that batch
  const batchAndPageIndices = useMemo(() => {
    const batchNum = Math.floor((currentPage - 1) / pagesPerBatch);
    const batchPageNum = (currentPage - 1) % pagesPerBatch;
    return { batchNum, batchPageNum };
  }, [currentPage, pagesPerBatch]);

  // Fetches a batch of data and stores it in the cache
  const fetchBatchData = useCallback(
    async (batchNum: number) => {
      // Prevents duplicate requests
      const requestId = `${effectiveRequestKey}#${batchNum}`;
      if (ongoingRequestsRef.current.has(requestId)) {
        return;
      }
      ongoingRequestsRef.current.add(requestId);

      try {
        // Build query params
        const params = new URLSearchParams({
          page_num: batchNum.toString(),
          page_size: (pagesPerBatch * itemsPerPage).toString(),
        });

        if (query) params.set("q", query);

        if (filter) {
          for (const [key, value] of Object.entries(filter)) {
            if (value === undefined || value === null) {
              continue;
            }
            if (Array.isArray(value)) {
              value.forEach((str) => {
                if (str !== undefined && str !== null) {
                  params.append(key, str.toString());
                }
              });
            } else {
              params.set(key, value.toString());
            }
          }
        }

        const responseData = await loadPageRef.current(params);

        // Validate response data structure
        if (
          !Array.isArray(
            responseData.items || typeof responseData.total_items !== "number"
          )
        ) {
          throw new Error(
            "Sorry, we encountered an issue with the data format. Please try again or contact support if the problem persists."
          );
        }

        // The search term or filters moved on while this was in flight.
        if (requestKeyRef.current !== effectiveRequestKey) {
          return;
        }

        setTotalItems(responseData.total_items);
        setTotalItemsExact(responseData.total_items_exact ?? true);

        // Splits a batch into pages
        const pagesInBatch = Array.from({ length: pagesPerBatch }, (_, i) => {
          const startIndex = i * itemsPerPage;
          return responseData.items.slice(
            startIndex,
            startIndex + itemsPerPage
          );
        });

        setCachedBatches((prev) => ({
          ...prev,
          [batchNum]: pagesInBatch,
        }));
      } catch (error) {
        if (requestKeyRef.current === effectiveRequestKey) {
          setError(error instanceof Error ? error : new Error(String(error)));
        }
      } finally {
        ongoingRequestsRef.current.delete(requestId);
      }
    },
    [effectiveRequestKey, pagesPerBatch, itemsPerPage, query, filter]
  );

  // Updates the URL with the current page number
  const updatePageUrl = useCallback(
    (page: number) => {
      if (currentPath && searchParams) {
        const params = new URLSearchParams(searchParams);
        params.set("page", page.toString());
        router.replace(`${currentPath}?${params.toString()}` as Route, {
          scroll: false,
        });
      }
    },
    [currentPath, router, searchParams]
  );

  // Updates the current page
  const goToPage = useCallback(
    (newPage: number) => {
      setCurrentPage(newPage);
      updatePageUrl(newPage);
    },
    [updatePageUrl]
  );

  // Loads the current and adjacent batches
  useEffect(() => {
    const { batchNum } = batchAndPageIndices;
    const nextBatchNum = batchNum + 1;
    const prevBatchNum = Math.max(batchNum - 1, 0);

    if (!cachedBatches[batchNum]) {
      setIsLoading(true);
      fetchBatchData(batchNum);
    }

    // Possible total number of items including the next batch
    const totalItemsIncludingNextBatch =
      nextBatchNum * pagesPerBatch * itemsPerPage;
    // Preload next batch if we're not on the last batch
    if (
      totalItemsIncludingNextBatch <= totalItems &&
      !cachedBatches[nextBatchNum]
    ) {
      fetchBatchData(nextBatchNum);
    }

    // Load previous batch if missing
    if (!cachedBatches[prevBatchNum]) {
      fetchBatchData(prevBatchNum);
    }

    // Ensure first batch is always loaded
    if (!cachedBatches[0]) {
      fetchBatchData(0);
    }
  }, [currentPage, cachedBatches, totalPages, pagesPerBatch, fetchBatchData]);

  // Updates current page data from the cache
  useEffect(() => {
    const { batchNum, batchPageNum } = batchAndPageIndices;

    const cachedBatch = cachedBatches[batchNum];
    if (cachedBatch !== undefined) {
      const cachedBatchPage = cachedBatch[batchPageNum];
      if (cachedBatchPage !== undefined) {
        setCurrentPageData(cachedBatchPage);
        setIsLoading(false);
      }
    }
  }, [currentPage, cachedBatches, pagesPerBatch]);

  // Implements periodic refresh
  useEffect(() => {
    if (!refreshIntervalInMs) return;

    const interval = setInterval(() => {
      const { batchNum } = batchAndPageIndices;
      fetchBatchData(batchNum);
    }, refreshIntervalInMs);

    return () => clearInterval(interval);
  }, [currentPage, pagesPerBatch, refreshIntervalInMs, fetchBatchData]);

  // Manually refreshes the current batch
  const refresh = useCallback(async () => {
    const { batchNum } = batchAndPageIndices;
    await fetchBatchData(batchNum);
  }, [currentPage, pagesPerBatch, fetchBatchData]);

  const updateItem = useCallback((itemId: T["id"], updater: (item: T) => T) => {
    setCachedBatches((prev) => {
      let didUpdate = false;
      const nextBatches = Object.fromEntries(
        Object.entries(prev).map(([batchNumber, pages]) => [
          batchNumber,
          pages.map((page) =>
            page.map((item) => {
              if (item.id !== itemId) return item;
              didUpdate = true;
              return updater(item);
            })
          ),
        ])
      );

      return didUpdate ? nextBatches : prev;
    });

    setCurrentPageData(
      (prev) =>
        prev?.map((item) => (item.id === itemId ? updater(item) : item)) ?? prev
    );
  }, []);

  // Cache invalidation
  useEffect(() => {
    setCachedBatches({});
    setCurrentPageData(null);
    setTotalItems(0);
    setTotalItemsExact(true);
    goToPage(1);
    setError(null);
  }, [currentPath, effectiveRequestKey]);

  return {
    currentPage,
    currentPageData,
    totalPages,
    totalItems,
    totalItemsExact,
    goToPage,
    refresh,
    updateItem,
    isLoading,
    error,
  };
}

export default usePaginatedFetch;
