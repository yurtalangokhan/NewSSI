"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import { type PaginatedCounts, type PaginatedCountItem } from "@/lib/langconnect";
import { cn } from "@/lib/utils";
import { snakeToHumanReadable } from "@/app/admin/kg/utils";
import { useTranslation } from "react-i18next";

const PAGE_SIZE = 10;

interface GraphStatsCardProps {
  collectionId: string | null;
  availableLabels: PaginatedCountItem[];
  availableRelTypes: PaginatedCountItem[];
  selectedLabels: Set<string>;
  selectedRelTypes: Set<string>;
  onToggleLabel: (label: string) => void;
  onToggleRelType: (relType: string) => void;
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
  disabled,
}: {
  name: string;
  count: number;
  selected: boolean;
  onToggle: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-08 border px-2.5 py-1.5 text-left text-xs transition-colors",
        disabled
          ? "border-border-01 bg-background-tint-00 text-text-03 opacity-50 cursor-not-allowed"
          : selected
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
  availableLabels,
  availableRelTypes,
  selectedLabels,
  selectedRelTypes,
  onToggleLabel,
  onToggleRelType,
  totalNodes,
  totalEdges,
  visibleNodes,
  visibleEdges,
}: GraphStatsCardProps) {
  const { t } = useTranslation();
  const [labelPage, setLabelPage] = useState(1);
  const [relPage, setRelPage] = useState(1);
  const [labelsSearch, setLabelsSearch] = useState("");
  const [relSearch, setRelSearch] = useState("");

  // Labels are filtered/paginated client-side from `availableLabels` (the
  // labels actually present in the currently loaded graph view), not fetched
  // from the collection-wide backend endpoint — that endpoint counts every
  // entity in the collection, which can list labels that never appear on
  // screen (e.g. absorbed as minority members of other clusters) and
  // selecting one would filter the graph down to nothing.
  const filteredLabelItems = useMemo(() => {
    const q = labelsSearch.trim().toLowerCase();
    if (!q) return availableLabels;
    return availableLabels.filter((item) => item.name.toLowerCase().includes(q));
  }, [availableLabels, labelsSearch]);

  const labelData: PaginatedCounts = useMemo(() => {
    const total = filteredLabelItems.length;
    const start = (labelPage - 1) * PAGE_SIZE;
    return {
      items: filteredLabelItems.slice(start, start + PAGE_SIZE),
      total,
      page: labelPage,
      page_size: PAGE_SIZE,
      has_next: start + PAGE_SIZE < total,
    };
  }, [filteredLabelItems, labelPage]);

  // With only one (or zero) entity label available in the current scope —
  // e.g. inside a single label's sub-clusters — there's nothing meaningful
  // to filter or search for, so disable the controls instead of offering a
  // filter that can only ever select everything or nothing.
  const labelsDisabled = availableLabels.length <= 1;

  useEffect(() => {
    setLabelPage(1);
    setLabelsSearch("");
  }, [availableLabels]);

  const handleLabelsSearchChange = useCallback((value: string) => {
    setLabelsSearch(value);
    setLabelPage(1);
  }, []);

  // Relationship types are filtered/paginated client-side from
  // `availableRelTypes` (the types actually present among edges in the
  // currently loaded graph view), not a separately-scoped backend query —
  // that endpoint could list types that don't belong to any edge actually
  // on screen (e.g. from the overview scope) after drilling into a
  // sub-cluster or neighborhood view.
  const filteredRelItems = useMemo(() => {
    const q = relSearch.trim().toLowerCase();
    if (!q) return availableRelTypes;
    return availableRelTypes.filter((item) => item.name.toLowerCase().includes(q));
  }, [availableRelTypes, relSearch]);

  const relData: PaginatedCounts = useMemo(() => {
    const total = filteredRelItems.length;
    const start = (relPage - 1) * PAGE_SIZE;
    return {
      items: filteredRelItems.slice(start, start + PAGE_SIZE),
      total,
      page: relPage,
      page_size: PAGE_SIZE,
      has_next: start + PAGE_SIZE < total,
    };
  }, [filteredRelItems, relPage]);

  useEffect(() => {
    setRelPage(1);
    setRelSearch("");
  }, [availableRelTypes]);

  const handleRelSearchChange = useCallback((value: string) => {
    setRelSearch(value);
    setRelPage(1);
  }, []);

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
            disabled={labelsDisabled}
            className="h-7 w-full rounded-06 border border-border-01 bg-background-tint-00 pl-7 pr-2 text-xs text-text-04 placeholder:text-text-03 focus:outline-none focus:ring-1 focus:ring-theme-primary-04 disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
        {labelsDisabled && labelData.items.length > 0 && (
          <Text as="p" mainContentMuted text03 className="text-[10px]">
            {t("admin.kg.onlyOneLabelInScope")}
          </Text>
        )}
        {labelData.items.length > 0 ? (
          <>
            <div className="flex flex-col gap-1">
              {labelData.items.map((item) => (
                <FilterBadge
                  key={item.name}
                  name={item.name}
                  count={item.count}
                  selected={selectedLabels.has(item.name)}
                  onToggle={() => onToggleLabel(item.name)}
                  disabled={labelsDisabled}
                />
              ))}
            </div>
            {/* Pagination */}
            {(labelPage > 1 || labelData.has_next) && (
              <div className="flex items-center justify-between pt-1">
                <button
                  disabled={labelPage <= 1}
                  onClick={() => setLabelPage((p) => p - 1)}
                  className="text-[10px] text-theme-primary-05 hover:underline disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t("admin.kg.prev")}
                </button>
                <Text as="span" mainContentMuted text03 className="text-[10px] tabular-nums">
                  {labelPage} / {Math.ceil(labelData.total / PAGE_SIZE)}
                </Text>
                <button
                  disabled={!labelData.has_next}
                  onClick={() => setLabelPage((p) => p + 1)}
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
        {relData.items.length > 0 ? (
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
                  onClick={() => setRelPage((p) => p - 1)}
                  className="text-[10px] text-theme-primary-05 hover:underline disabled:opacity-40 disabled:pointer-events-none"
                >
                  {t("admin.kg.prev")}
                </button>
                <Text as="span" mainContentMuted text03 className="text-[10px] tabular-nums">
                  {relPage} / {Math.ceil(relData.total / PAGE_SIZE)}
                </Text>
                <button
                  disabled={!relData.has_next}
                  onClick={() => setRelPage((p) => p + 1)}
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
