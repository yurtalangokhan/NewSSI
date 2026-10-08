"use client";

import { useTranslation } from "react-i18next";
import { Tag } from "@opal/components";
import { SvgArrowRight, SvgNetworkGraph, SvgServer } from "@opal/icons";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import EntityDot from "@/sections/knowledge-search/components/EntityDot";
import EntityLabelBadge from "@/sections/knowledge-search/components/EntityLabelBadge";
import RelevanceMeter from "@/sections/knowledge-search/components/RelevanceMeter";
import SearchHitCardFrame from "@/sections/knowledge-search/components/SearchHitCardFrame";
import type { KnowledgeSearchHit } from "@/lib/api/domains/knowledge/knowledge-search-types";

interface EntityHitCardProps {
  hit: KnowledgeSearchHit;
  selected: boolean;
  /** Label the card as an entity (hybrid results mix kinds). */
  showKind: boolean;
  onOpen: (hit: KnowledgeSearchHit) => void;
}

/** A matched graph entity: type, collection, and its nearest relations. */
export default function EntityHitCard({
  hit,
  selected,
  showKind,
  onOpen,
}: EntityHitCardProps) {
  const { t } = useTranslation();
  const entity = hit.entity;
  if (!entity) return null;

  return (
    <SearchHitCardFrame selected={selected} onOpen={() => onOpen(hit)}>
      <span className="flex min-w-0 items-center gap-2.5">
        <EntityDot label={entity.label} />
        <Text
          as="span"
          mainUiAction
          text05
          className={cn(
            "min-w-0 flex-1 truncate",
            selected && "text-action-link-05"
          )}
        >
          {entity.name}
        </Text>
        <RelevanceMeter value={hit.relevance} />
      </span>
      <span className="flex flex-wrap items-center gap-1.5">
        {showKind && (
          <Tag
            icon={SvgNetworkGraph}
            title={t("knowledgeSearch.hit.entity")}
            color="purple"
          />
        )}
        <EntityLabelBadge label={entity.label} />
        {entity.matched && (
          <Tag title={t("knowledgeSearch.hit.matched")} color="green" />
        )}
        <Tag icon={SvgServer} title={hit.collectionName} />
        <Text as="span" secondaryBody text02>
          {t("knowledgeSearch.hit.neighbors", {
            count: entity.neighborCount,
          })}
        </Text>
      </span>
      {entity.relations.length > 0 && (
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {entity.relations.map((relation) => (
            <span
              key={`${relation.direction}-${relation.type}-${relation.nodeId}`}
              className="flex min-w-0 items-center gap-1.5"
            >
              <Text as="span" secondaryMono text03 className="shrink-0">
                {relation.direction === "in"
                  ? `← ${relation.type}`
                  : relation.type}
              </Text>
              {relation.direction === "out" && (
                <SvgArrowRight className="h-3 w-3 shrink-0 stroke-text-02" />
              )}
              <Text as="span" secondaryBody text04 className="min-w-0 truncate">
                {relation.nodeName}
              </Text>
            </span>
          ))}
        </span>
      )}
    </SearchHitCardFrame>
  );
}
