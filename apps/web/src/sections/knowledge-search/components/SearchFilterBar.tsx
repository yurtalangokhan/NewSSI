"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { SvgFileText, SvgNetworkGraph, SvgServer } from "@opal/icons";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import Text from "@/refresh-components/texts/Text";
import FacetFilterPopover, {
  type FacetOption,
} from "@/sections/knowledge-search/components/FacetFilterPopover";
import SearchSettingsPopover from "@/sections/knowledge-search/components/SearchSettingsPopover";
import type {
  KnowledgeFacetValue,
  KnowledgeSearchSource,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

interface SearchFilterBarProps {
  sources: readonly KnowledgeSearchSource[];
  collectionIds: readonly string[];
  onCollectionToggle: (collectionId: string) => void;
  onCollectionsClear: () => void;
  fileTypes: readonly KnowledgeFacetValue[];
  selectedFileTypes: readonly string[];
  onFileTypeToggle: (value: string) => void;
  onFileTypesClear: () => void;
  entityLabels: readonly KnowledgeFacetValue[];
  selectedEntityLabels: readonly string[];
  onEntityLabelToggle: (value: string) => void;
  onEntityLabelsClear: () => void;
  limit: number;
  onLimitChange: (limit: number) => void;
  /** A refresh is running over an existing result; replaces the meta line. */
  isSearching?: boolean;
  /** Filtered result count and search time, once a result arrived. */
  total?: number;
  elapsedMs?: number;
}

function facetOptions(
  values: readonly KnowledgeFacetValue[],
  format: (value: string) => string = (value) => value
): FacetOption[] {
  return values.map(({ value, count }) => ({
    value,
    count,
    label: format(value),
  }));
}

/** Collection, file type and entity type filters plus search settings. */
export default function SearchFilterBar({
  sources,
  collectionIds,
  onCollectionToggle,
  onCollectionsClear,
  fileTypes,
  selectedFileTypes,
  onFileTypeToggle,
  onFileTypesClear,
  entityLabels,
  selectedEntityLabels,
  onEntityLabelToggle,
  onEntityLabelsClear,
  limit,
  onLimitChange,
  isSearching = false,
  total,
  elapsedMs,
}: SearchFilterBarProps) {
  const { t } = useTranslation();

  const collectionOptions = useMemo<FacetOption[]>(
    () =>
      sources.map((source) => ({
        value: source.id,
        label: source.name,
        description: source.hasGraph
          ? t("knowledgeSearch.rail.sourceType.graph")
          : t(`knowledgeSearch.rail.sourceType.${source.sourceType}`),
      })),
    [sources, t]
  );

  return (
    <div className="flex w-full flex-wrap items-center gap-1 border-b border-border-01 pb-3">
      <FacetFilterPopover
        icon={SvgServer}
        label={t("knowledgeSearch.filters.collection")}
        options={collectionOptions}
        selected={collectionIds}
        onToggle={onCollectionToggle}
        onClear={onCollectionsClear}
        searchPlaceholder={t("knowledgeSearch.filters.searchCollections")}
      />
      <FacetFilterPopover
        icon={SvgFileText}
        label={t("knowledgeSearch.filters.fileType")}
        options={facetOptions(fileTypes, (value) => value.toUpperCase())}
        selected={selectedFileTypes}
        onToggle={onFileTypeToggle}
        onClear={onFileTypesClear}
      />
      <FacetFilterPopover
        icon={SvgNetworkGraph}
        label={t("knowledgeSearch.filters.entityType")}
        options={facetOptions(entityLabels)}
        selected={selectedEntityLabels}
        onToggle={onEntityLabelToggle}
        onClear={onEntityLabelsClear}
      />
      <div className="flex-1" />
      {isSearching ? (
        <span className="flex items-center gap-2">
          <SimpleLoader className="h-4 w-4 shrink-0" />
          <Text as="span" secondaryBody text03>
            {t("knowledgeSearch.results.loading")}
          </Text>
        </span>
      ) : (
        total !== undefined &&
        elapsedMs !== undefined && (
          <Text as="span" secondaryBody text03 className="tabular-nums">
            {t("knowledgeSearch.meta", { count: total, ms: elapsedMs })}
          </Text>
        )
      )}
      <SearchSettingsPopover limit={limit} onLimitChange={onLimitChange} />
    </div>
  );
}
