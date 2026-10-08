"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgAlertTriangle, SvgRefreshCw, SvgSearch } from "@opal/icons";
import { cn } from "@/lib/utils";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import DocumentHitCard from "@/sections/knowledge-search/components/DocumentHitCard";
import EntityHitCard from "@/sections/knowledge-search/components/EntityHitCard";
import ResultListSkeleton from "@/sections/knowledge-search/components/ResultListSkeleton";
import SearchNotice from "@/sections/knowledge-search/components/SearchNotice";
import {
  remainingCount,
  showMoreAction,
  visibleHits,
} from "@/sections/knowledge-search/model/resultsView";
import type {
  KnowledgeSearchHit,
  KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

interface ResultListProps {
  response: KnowledgeSearchResponse | undefined;
  error: Error | undefined;
  isLoading: boolean;
  /** A search is in flight; existing hits stay visible but marked as loading. */
  isSearching: boolean;
  query: string;
  visibleCount: number;
  limit: number;
  selectedHitId: string | null;
  hasFilters: boolean;
  onOpen: (hit: KnowledgeSearchHit) => void;
  onShowMore: () => void;
  onRetry: () => void;
  onResetFilters: () => void;
}

/** Why hybrid results carry no graph part: a store outage or no graph access. */
function graphNoticeKey(response: KnowledgeSearchResponse) {
  if (response.kind !== "hybrid" || response.graphAvailable) return null;
  return response.graphUnavailable
    ? "knowledgeSearch.results.graphStoreUnavailable"
    : "knowledgeSearch.results.graphUnavailable";
}

/** Ranked result cards with paging, loading, empty, and error states. */
export default function ResultList({
  response,
  error,
  isLoading,
  isSearching,
  query,
  visibleCount,
  limit,
  selectedHitId,
  hasFilters,
  onOpen,
  onShowMore,
  onRetry,
  onResetFilters,
}: ResultListProps) {
  const { t } = useTranslation();

  if (error && !response) {
    return (
      <div role="alert">
        <EmptyMessage
          icon={SvgAlertTriangle}
          title={t("knowledgeSearch.results.error")}
          description={error.message}
        >
          <div>
            <Button
              icon={SvgRefreshCw}
              prominence="secondary"
              onClick={onRetry}
            >
              {t("knowledgeSearch.results.retry")}
            </Button>
          </div>
        </EmptyMessage>
      </div>
    );
  }

  if (!response) {
    return isLoading || isSearching ? <ResultListSkeleton /> : null;
  }

  const failedCollections = response.collections.filter(
    (collection) => collection.status === "failed"
  ).length;
  const graphNotice = graphNoticeKey(response);
  const action = showMoreAction(response, visibleCount, limit);
  const showKind = response.kind === "hybrid";

  return (
    <div className="flex w-full min-w-0 flex-col gap-2" aria-busy={isSearching}>
      {failedCollections > 0 && (
        <SearchNotice>
          {t("knowledgeSearch.results.collectionsFailed", {
            count: failedCollections,
          })}
        </SearchNotice>
      )}
      {graphNotice && <SearchNotice>{t(graphNotice)}</SearchNotice>}

      {response.hits.length === 0 ? (
        <EmptyMessage
          icon={SvgSearch}
          title={
            hasFilters
              ? t("knowledgeSearch.results.emptyForFilters")
              : t("knowledgeSearch.results.empty")
          }
          description={
            hasFilters
              ? undefined
              : t("knowledgeSearch.results.emptyDescription")
          }
        >
          {hasFilters && (
            <div>
              <Button prominence="secondary" onClick={onResetFilters}>
                {t("knowledgeSearch.results.resetFilters")}
              </Button>
            </div>
          )}
        </EmptyMessage>
      ) : (
        <ul
          className={cn(
            "flex flex-col gap-2 transition-opacity",
            isSearching && "opacity-60"
          )}
        >
          {visibleHits(response.hits, visibleCount).map((hit) => (
            <li key={`${hit.kind}:${hit.collectionId}:${hit.id}`}>
              {hit.kind === "document" ? (
                <DocumentHitCard
                  hit={hit}
                  query={query}
                  selected={hit.id === selectedHitId}
                  showKind={showKind}
                  onOpen={onOpen}
                />
              ) : (
                <EntityHitCard
                  hit={hit}
                  selected={hit.id === selectedHitId}
                  showKind={showKind}
                  onOpen={onOpen}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {action !== null && (
        <div className="px-4 pt-2">
          <Button prominence="secondary" onClick={onShowMore}>
            {t("knowledgeSearch.results.showMore", {
              count: remainingCount(response, visibleCount),
            })}
          </Button>
        </div>
      )}
    </div>
  );
}
