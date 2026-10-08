"use client";

import { useTranslation } from "react-i18next";
import { Tag } from "@opal/components";
import { SvgFileText, SvgServer } from "@opal/icons";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import { HighlightedText } from "@/refresh-components/texts/HighlightedText";
import FileTypeBadge from "@/sections/knowledge-search/components/FileTypeBadge";
import RelevanceMeter from "@/sections/knowledge-search/components/RelevanceMeter";
import SearchHitCardFrame from "@/sections/knowledge-search/components/SearchHitCardFrame";
import { documentTitle } from "@/sections/knowledge-search/model/resultsView";
import type { KnowledgeSearchHit } from "@/lib/api/domains/knowledge/knowledge-search-types";

interface DocumentHitCardProps {
  hit: KnowledgeSearchHit;
  query: string;
  selected: boolean;
  /** Label the card as a passage (hybrid results mix kinds). */
  showKind: boolean;
  onOpen: (hit: KnowledgeSearchHit) => void;
}

/** A document passage: file, collection, location, and the matched text. */
export default function DocumentHitCard({
  hit,
  query,
  selected,
  showKind,
  onOpen,
}: DocumentHitCardProps) {
  const { t } = useTranslation();
  const document = hit.document;
  if (!document) return null;
  const title = documentTitle(document) ?? t("knowledgeSearch.hit.untitled");

  return (
    <SearchHitCardFrame selected={selected} onOpen={() => onOpen(hit)}>
      <span className="flex min-w-0 items-center gap-2.5">
        <FileTypeBadge fileType={document.fileType} />
        <Text
          as="span"
          mainUiAction
          text05
          className={cn(
            "min-w-0 flex-1 truncate",
            selected && "text-action-link-05"
          )}
        >
          {title}
        </Text>
        <RelevanceMeter value={hit.relevance} />
      </span>
      <span className="flex flex-wrap items-center gap-1.5">
        {showKind && (
          <Tag
            icon={SvgFileText}
            title={t("knowledgeSearch.hit.passage")}
            color="blue"
          />
        )}
        <Tag icon={SvgServer} title={hit.collectionName} />
        {document.page !== null && (
          <Tag title={t("knowledgeSearch.hit.page", { page: document.page })} />
        )}
        {document.section && <Tag title={`# ${document.section}`} />}
      </span>
      <Text as="span" secondaryBody text04 className="line-clamp-2">
        <HighlightedText text={document.content} query={query} />
      </Text>
    </SearchHitCardFrame>
  );
}
