import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import type {
  EvidenceGraph,
  EvidenceGraphNode,
} from "@/lib/api/domains/chat/knowledge-evidence-types";
import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";
import {
  formatPropertyValue,
  visibleProperties,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";
import { relationCount } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/graphSelection";
import { useScoreFormatter } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/useScoreFormatter";

interface EvidenceEntityDetailsProps {
  graph: EvidenceGraph;
  node: EvidenceGraphNode;
  /** Shown under the details, e.g. the entity's relations. */
  children?: ReactNode;
}

/** Rank-fusion scores are tiny (0,0098), so they keep four decimals. */
const MATCH_SCORE_FRACTION_DIGITS = 4;

/** One entity: its type, why it is in the result, and its properties. */
export function EvidenceEntityDetails({
  graph,
  node,
  children,
}: EvidenceEntityDetailsProps) {
  const { t } = useTranslation();
  const formatMatchScore = useScoreFormatter(MATCH_SCORE_FRACTION_DIGITS);
  const color = entityColor(node.label);
  const connections = relationCount(graph, node.id);
  const properties = visibleProperties(node.properties);

  return (
    <section className="flex min-w-0 flex-col gap-2 rounded-08 border border-border-01 bg-background-neutral-00 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Text
          as="span"
          secondaryMono
          className="rounded-04 px-1.5"
          style={{
            background: entityColorVar(color, "01"),
            color: entityColorVar(color, "05"),
          }}
        >
          {node.label}
        </Text>
        <Text as="h3" mainUiAction text05>
          {node.name}
        </Text>
      </div>
      <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
        <Text as="span" secondaryBody text03>
          {t("knowledgeCard.match")}
        </Text>
        <Text as="span" secondaryBody text04>
          {node.matched
            ? t("knowledgeCard.matchedDirectly")
            : t("knowledgeCard.expanded")}
          {node.matched && node.score !== null
            ? ` · ${t("knowledgeCard.matchScore", {
                score: formatMatchScore(node.score),
              })}`
            : ""}
        </Text>
        <Text as="span" secondaryBody text03>
          {t("knowledgeCard.connections")}
        </Text>
        <Text as="span" secondaryBody text04>
          {t("knowledgeCard.connectionCount", { count: connections })}
        </Text>
        {properties.map(([key, value]) => (
          <PropertyRow
            key={key}
            name={key}
            value={formatPropertyValue(value)}
          />
        ))}
      </div>
      {children}
    </section>
  );
}

interface PropertyRowProps {
  name: string;
  value: string;
}

function PropertyRow({ name, value }: PropertyRowProps) {
  return (
    <>
      <Text as="span" secondaryBody text03>
        {name.replace(/_/g, " ")}
      </Text>
      <Text as="span" secondaryBody text04 className="break-words">
        {value}
      </Text>
    </>
  );
}
