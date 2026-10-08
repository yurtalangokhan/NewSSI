"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import { Button } from "@opal/components";
import { SvgArrowRight, SvgSearchMenu } from "@opal/icons";
import { cn } from "@/lib/utils";
import FadingEdgeContainer from "@/refresh-components/FadingEdgeContainer";
import Text from "@/refresh-components/texts/Text";
import CollectionFacetRow from "@/sections/knowledge-search/components/CollectionFacetRow";
import EntityColorDot from "@/sections/knowledge-search/components/EntityColorDot";
import LabeledSection from "@/sections/knowledge-search/components/LabeledSection";
import KnowledgeForceGraph from "@/refresh-components/knowledge-graph/KnowledgeForceGraph";
import {
  sourcePresentation,
  sourceSubtitle,
} from "@/sections/knowledge-search/components/sourcePresentation";
import {
  hitCollections,
  hitCounts,
} from "@/sections/knowledge-search/model/resultsView";
import type {
  KnowledgeGraph,
  KnowledgeSearchResponse,
  KnowledgeSearchSource,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

const MINI_GRAPH_HEIGHT = 240;

interface SearchSummaryRailProps {
  response: KnowledgeSearchResponse;
  sources: readonly KnowledgeSearchSource[];
  /** The graph as currently displayed (expansions included). */
  graph: KnowledgeGraph;
  collectionIds: readonly string[];
  onCollectionsChange: (collectionIds: readonly string[]) => void;
  selectedEntityLabels: readonly string[];
  onEntityLabelToggle: (label: string) => void;
  onOpenGraph: () => void;
}

/** Summary, collection facet, matched subgraph, and entity types. */
export default function SearchSummaryRail({
  response,
  sources,
  graph,
  collectionIds,
  onCollectionsChange,
  selectedEntityLabels,
  onEntityLabelToggle,
  onOpenGraph,
}: SearchSummaryRailProps) {
  const { t } = useTranslation();
  const counts = hitCounts(response);
  const total = counts.documents + counts.entities;
  const sourcesById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources]
  );

  return (
    <aside
      aria-label={t("knowledgeSearch.rail.label")}
      className="flex min-w-0 flex-col gap-6"
    >
      <div className="flex flex-col gap-2.5 border-b border-border-01 pb-5">
        <Text as="p" mainUiAction text05>
          {t("knowledgeSearch.rail.summary", {
            count: total,
            collections: counts.collections,
          })}
        </Text>
        {total > 0 && (
          <div className="flex h-1.5 gap-0.5 overflow-hidden rounded-full">
            <span
              className="bg-theme-blue-05"
              style={{ flexGrow: counts.documents }}
            />
            <span
              className="bg-theme-purple-05"
              style={{ flexGrow: counts.entities }}
            />
          </div>
        )}
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-theme-blue-05" />
            <Text as="span" secondaryBody text03>
              {t("knowledgeSearch.rail.documents", {
                count: counts.documents,
              })}
            </Text>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-theme-purple-05" />
            <Text as="span" secondaryBody text03>
              {t("knowledgeSearch.rail.entities", { count: counts.entities })}
            </Text>
          </span>
        </div>
      </div>

      <LabeledSection title={t("knowledgeSearch.rail.collections")}>
        <FadingEdgeContainer
          direction="bottom"
          className="max-h-[24rem] overflow-y-auto overscroll-contain pr-0.5"
          fadeClassName="from-background-tint-00"
        >
          <div
            role="group"
            aria-label={t("knowledgeSearch.rail.collections")}
            className="flex flex-col gap-2"
          >
            <CollectionFacetRow
              icon={SvgSearchMenu}
              tone="bg-background-tint-03 stroke-text-04"
              name={t("knowledgeSearch.rail.allSources")}
              subtitle={t("knowledgeSearch.filters.collectionCount", {
                count: counts.collections,
              })}
              count={total}
              pressed={collectionIds.length === 0}
              onClick={() => onCollectionsChange([])}
            />
            {hitCollections(response).map((collection) => {
              const source = sourcesById.get(collection.id);
              const presentation = sourcePresentation(source);
              const pressed =
                collectionIds.length === 1 &&
                collectionIds[0] === collection.id;
              return (
                <CollectionFacetRow
                  key={collection.id}
                  icon={presentation.icon}
                  tone={presentation.tone}
                  name={collection.name}
                  subtitle={sourceSubtitle(source, t)}
                  count={collection.documentHits + collection.entityHits}
                  pressed={pressed}
                  failed={collection.status === "failed"}
                  onClick={() =>
                    onCollectionsChange(pressed ? [] : [collection.id])
                  }
                />
              );
            })}
          </div>
        </FadingEdgeContainer>
      </LabeledSection>

      {graph.nodes.length > 0 && (
        <LabeledSection title={t("knowledgeSearch.rail.matchedSubgraph")}>
          <div className="flex flex-col gap-2 rounded-16 border border-border-01 bg-background-neutral-01 p-2">
            <KnowledgeForceGraph
              graph={graph}
              height={MINI_GRAPH_HEIGHT}
              interactive={false}
              ariaLabel={t("knowledgeSearch.graph.label")}
            />
            <div className="flex items-center justify-between gap-2 px-1">
              <span className="flex items-center gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-text-04" />
                  <Text as="span" secondaryBody text03>
                    {t("knowledgeSearch.rail.matched")}
                  </Text>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full border-[1.5px] border-text-03" />
                  <Text as="span" secondaryBody text03>
                    {t("knowledgeSearch.rail.neighbor")}
                  </Text>
                </span>
              </span>
              <Button
                rightIcon={SvgArrowRight}
                prominence="tertiary"
                size="md"
                onClick={onOpenGraph}
              >
                {t("knowledgeSearch.rail.openGraph")}
              </Button>
            </div>
          </div>
        </LabeledSection>
      )}

      {response.facets.entityLabels.length > 0 && (
        <LabeledSection title={t("knowledgeSearch.rail.entityTypes")}>
          <div className="flex flex-wrap gap-1.5">
            {response.facets.entityLabels.map(({ value, count }) => {
              const pressed = selectedEntityLabels.includes(value);
              return (
                <Interactive.Base
                  key={value}
                  variant="select"
                  prominence="light"
                  selected={pressed}
                  group="group/EntityChip"
                  onClick={() => onEntityLabelToggle(value)}
                >
                  <Interactive.Container
                    type="button"
                    aria-pressed={pressed}
                    heightVariant="fit"
                    roundingVariant="compact"
                  >
                    <span
                      className={cn(
                        "flex items-center gap-1.5 rounded-08 border px-2 py-1 transition-colors",
                        pressed
                          ? "border-action-link-05 bg-action-link-01"
                          : "border-border-01 bg-background-neutral-01 group-hover/EntityChip:bg-background-tint-01"
                      )}
                    >
                      <EntityColorDot label={value} />
                      <Text
                        as="span"
                        secondaryAction
                        text04
                        className={cn(pressed && "text-action-link-05")}
                      >
                        {value}
                      </Text>
                      <Text
                        as="span"
                        secondaryMono
                        text02
                        className="tabular-nums"
                      >
                        {count}
                      </Text>
                    </span>
                  </Interactive.Container>
                </Interactive.Base>
              );
            })}
          </div>
        </LabeledSection>
      )}
    </aside>
  );
}
