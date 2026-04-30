"use client";

import { useState, useEffect, useCallback } from "react";
import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import {
  fetchGraphLabelsPaginated,
  fetchGraphRelTypesPaginated,
  type PaginatedCounts,
} from "@/lib/langconnect";
import { cn } from "@/lib/utils";
import { ThreeDotsLoader } from "@/components/Loading";
import { snakeToHumanReadable, useDebounce } from "@/app/admin/kg/utils";
import { useTranslation } from "react-i18next";

const PAGE_SIZE = 10;

interface GraphStatsCardProps {
  collectionId: string | null;
  selectedLabels: Set<string>;
  selectedRelTypes: Set<string>;
  onToggleLabel: (label: string) => void;
  onToggleRelType: (relType: string) => void;
  scopeLabel?: string;
  totalNodes: number;
  totalEdges: number;
  visibleNodes: number;
  visibleEdges: number;
}

function FilterBadge({
  name,
  count,
  selected,
  onToggle,
}: {
  name: string;
  count: number;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-08 border px-2.5 py-1.5 text-left text-xs transition-colors",
        selected
          ? "border-theme-primary-04 bg-theme-primary-01 text-theme-primary-07"
          : "border-border-01 bg-background-tint-00 hover:bg-background-neutral-01 text-text-04"
      )}
    >
      <span className="truncate capitalize">{snakeToHumanReadable(name)}</span>
      <span
        className={cn(
          "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums",
          selected
            ? "bg-theme-primary-03 text-theme-primary-07"
            : "bg-background-neutral-01 text-text-03"
        )}
      >
        {count.toLocaleString()}
      </span>
    </button>
  );
}

export default function GraphStatsCard({
  collectionId,
  selectedLabels,
  selectedRelTypes,
  onToggleLabel,
  onToggleRelType,
  scopeLabel,
  totalNodes,
  totalEdges,
  visibleNodes,
  visibleEdges,
}: GraphStatsCardProps) {
  const { t } = useTranslation();
  const [labelData, setLabelData] = useState<PaginatedCounts | null>(null);
  const [relData, setRelData] = useState<PaginatedCounts | null>(null);
  const [labelsLoading, setLabelsLoading] = useState(false);
  const [relLoading, setRelLoading] = useState(false);
  const [labelPage, setLabelPage] = useState(1);
  const [relPage, setRelPage] = useState(1);
  const [labelsSearch, setLabelsSearch] = useState("");
  const [relSearch, setRelSearch] = useState("");

  const relTypeFilter = Array.from(selectedRelTypes);
  const labelFilter = Array.from(selectedLabels);
  const relTypeFilterKey = relTypeFilter.join(",");
  const labelFilterKey = labelFilter.join(",");

  const loadLabels = useCallback(
    async (page: number, search: string) => {
      if (!collectionId) return;
      setLabelsLoading(true);
      try {
        const data = await fetchGraphLabelsPaginated(collectionId, {
          page,
          pageSize: PAGE_SIZE,
          search: search || undefined,
          scopeLabel,
          relTypeFilter: relTypeFilter.length ? relTypeFilter : undefined,
        });
        setLabelData(data);
      } catch {
        // ignore
      } finally {
        setLabelsLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [collectionId, scopeLabel, relTypeFilterKey]
  );

  const loadRelTypes = useCallback(
    async (page: number, search: string) => {
      if (!collectionId) return;
      setRelLoading(true);
      try {
        const data = await fetchGraphRelTypesPaginated(collectionId, {
          page,
          pageSize: PAGE_SIZE,
          search: search || undefined,
          scopeLabel,
          labelFilter: labelFilter.length ? labelFilter : undefined,
        });
        setRelData(data);
      } catch {
        // ignore
      } finally {
        setRelLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [collectionId, scopeLabel, labelFilterKey]
  );

  // Reset pages and reload when collection/scope/filters change
  useEffect(() => {
    setLabelPage(1);
    setLabelsSearch("");
    loadLabels(1, "");
  }, [loadLabels]);

  useEffect(() => {
    setRelPage(1);
    setRelSearch("");
    loadRelTypes(1, "");
  }, [loadRelTypes]);

  const debouncedLoadLabels = useDebounce(
    useCallback((value: string) => {
      setLabelPage(1);
      loadLabels(1, value);
    }, [loadLabels]),
    300
  );

  const handleLabelsSearchChange = useCallback(
    (value: string) => {
      setLabelsSearch(value);
      debouncedLoadLabels(value);
    },
    [debouncedLoadLabels]
  );

  const debouncedLoadRelTypes = useDebounce(
    useCallback((value: string) => {
      setRelPage(1);
      loadRelTypes(1, value);
    }, [loadRelTypes]),
    300
  );

  const handleRelSearchChange = useCallback(
    (value: string) => {
      setRelSearch(value);
      debouncedLoadRelTypes(value);
    },
    [debouncedLoadRelTypes]
  );

  if (!collectionId) return null;

  return (
    <CardSection className="flex flex-col gap-4 overflow-y-auto max-h-[700px]">
      {/* Counts */}
      <div className="flex flex-col gap-1.5">
        <Text as="p" headingH3 text05>
          {t("admin.kg.graphStats")}
        </Text>
        <div className="flex flex-wrap gap-2">
          <div className="flex items-center gap-1.5 rounded-full border border-border-01 px-2.5 py-1">
            <Text as="span" mainContentMuted text03 className="text-xs">{t("admin.kg.nodes")}</Text>
            <Text as="span" mainUiAction text04 className="text-xs font-semibold tabular-nums">
              {visibleNodes < totalNodes
                ? `${visibleNodes.toLocaleString()} / ${totalNodes.toLocaleString()}`
                : totalNodes.toLocaleString()}
            </Text>
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-border-01 px-2.5 py-1">
            <Text as="span" mainContentMuted text03 className="text-xs">{t("admin.kg.edges")}</Text>
            <Text as="span" mainUiAction text04 className="text-xs font-semibold tabular-nums">
              {visibleEdges < totalEdges
                ? `${visibleEdges.toLocaleString()} / ${totalEdges.toLocaleString()}`
                : totalEdges.toLocaleString()}
            </Text>
          </div>
        </div>
      </div>

      {/* Entity Labels */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Text
            as="p"
            mainContentMuted
            text03
            className="text-xs font-medium uppercase tracking-wide"
          >
            {t("admin.kg.entityLabels")}
            {labelData && (
              <span className="ml-1 font-normal normal-case opacity-60">
                ({labelData.total})
              </span>
            )}
          </Text>
          {selectedLabels.size > 0 && (
            <button
              onClick={() => Array.from(selectedLabels).forEach(onToggleLabel)}
              className="text-[10px] text-theme-primary-05 hover:underline"
            >
              {t("admin.kg.clear")}
            </button>
          )}
        </div>
        {/* Search */}
        <div className="relative">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-text-03 pointer-events-none">
            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </svg>
          </span>
          <input
            type="text"
            placeholder={t("admin.kg.searchLabelsPlaceholder")}
            value={labelsSearch}
            onChange={(e) => handleLabelsSearchChange(e.target.value)}
            className="h-7 w-full rounded-06 border border-border-01 bg-background-tint-00 pl-7 pr-2 text-xs text-text-04 placeholder:text-text-03 focus:outline-none focus:ring-1 focus:ring-theme-primary-04"
          />
        </div>
        {labelsLoading ? (
          <ThreeDotsLoader />
        ) : labelData && labelData.items.length > 0 ? (
          <>
            <div className="flex flex-col gap-1">
              {labelData.items.map((item) => (
                <FilterBadge
                  key={item.name}
                  name={item.name}
                  count={item.count}
                  selected={selectedLabels.has(item.name)}
                  onToggle={() => onToggleLabel(item.name)}
                />
              ))}
            </div>
            {/* Pagination */}
            {(labelPage > 1 || labelData.has_next) && (
              <div className="flex items-center justify-between pt-1">
                <button
                  disabled={labelPage <= 1}
                  onClick={() => {
                    const p = labelPage - 1;
                    setLabelPage(p);
                    loadLabels(p, labelsSearch);
                  }}
                  className="text-[10px] text-theme-primary-05 hover:underline disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t("admin.kg.prev")}
                </button>
                <Text as="span" mainContentMuted text03 className="text-[10px] tabular-nums">
                  {labelPage} / {Math.ceil(labelData.total / PAGE_SIZE)}
                </Text>
                <button
                  disabled={!labelData.has_next}
                  onClick={() => {
                    const p = labelPage + 1;
                    setLabelPage(p);
                    loadLabels(p, labelsSearch);
                  }}
                  className="text-[10px] text-theme-primary-05 hover:underline disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t("admin.kg.next")}
                </button>
              </div>
            )}
          </>
        ) : (
          <Text as="p" mainContentMuted text03 className="text-xs">
            {labelsSearch ? t("admin.kg.noMatchingLabels") : t("admin.kg.noLabels")}
          </Text>
        )}
      </div>

      {/* Relationship Types */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Text
            as="p"
            mainContentMuted
            text03
            className="text-xs font-medium uppercase tracking-wide"
          >
            {t("admin.kg.relationshipTypes")}
            {relData && (
              <span className="ml-1 font-normal normal-case opacity-60">
                ({relData.total})
              </span>
            )}
          </Text>
          {selectedRelTypes.size > 0 && (
            <button
              onClick={() => Array.from(selectedRelTypes).forEach(onToggleRelType)}
              className="text-[10px] text-theme-primary-05 hover:underline"
            >
              {t("admin.kg.clear")}
            </button>
          )}
        </div>
        {/* Search */}
        <div className="relative">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-text-03 pointer-events-none">
            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </svg>
          </span>
          <input
            type="text"
            placeholder={t("admin.kg.searchRelationshipTypesPlaceholder")}
            value={relSearch}
            onChange={(e) => handleRelSearchChange(e.target.value)}
            className="h-7 w-full rounded-06 border border-border-01 bg-background-tint-00 pl-7 pr-2 text-xs text-text-04 placeholder:text-text-03 focus:outline-none focus:ring-1 focus:ring-theme-primary-04"
          />
        </div>
        {relLoading ? (
          <ThreeDotsLoader />
        ) : relData && relData.items.length > 0 ? (
          <>
            <div className="flex flex-col gap-1">
              {relData.items.map((item) => (
                <FilterBadge
                  key={item.name}
                  name={item.name}
                  count={item.count}
                  selected={selectedRelTypes.has(item.name)}
                  onToggle={() => onToggleRelType(item.name)}
                />
              ))}
            </div>
            {(relPage > 1 || relData.has_next) && (
              <div className="flex items-center justify-between pt-1">
                <button
                  disabled={relPage <= 1}
                  onClick={() => {
                    const p = relPage - 1;
                    setRelPage(p);
                    loadRelTypes(p, relSearch);
                  }}
                  className="text-[10px] text-theme-primary-05 hover:underline disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t("admin.kg.prev")}
                </button>
                <Text as="span" mainContentMuted text03 className="text-[10px] tabular-nums">
                  {relPage} / {Math.ceil(relData.total / PAGE_SIZE)}
                </Text>
                <button
                  disabled={!relData.has_next}
                  onClick={() => {
                    const p = relPage + 1;
                    setRelPage(p);
                    loadRelTypes(p, relSearch);
                  }}
                  className="text-[10px] text-theme-primary-05 hover:underline disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t("admin.kg.next")}
                </button>
              </div>
            )}
          </>
        ) : (
          <Text as="p" mainContentMuted text03 className="text-xs">
            {relSearch
              ? t("admin.kg.noMatchingRelationshipTypes")
              : t("admin.kg.noRelationshipTypes")}
          </Text>
        )}
      </div>
    </CardSection>
  );
}
