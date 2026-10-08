import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import { formatRunTime } from "@/components/flow-canvas/utils/formatRunTime";
import { groupSources } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";
import {
  KnowledgeCall,
  isGraphCall,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/knowledgeCalls";

interface KnowledgeCallHeaderProps {
  call: KnowledgeCall;
}

/** "Searched documents · 5 chunks · 2 documents · HR Policies · 0.42s". */
export function KnowledgeCallHeader({ call }: KnowledgeCallHeaderProps) {
  const { t } = useTranslation();
  const { evidence } = call;
  const graph = isGraphCall(call);

  const title =
    call.status === "running"
      ? t("knowledgeCard.searching")
      : graph
        ? t("knowledgeCard.searchedGraph")
        : t("knowledgeCard.searchedDocuments");

  const facts: string[] = [];
  if (evidence && evidence.graph) {
    facts.push(
      t("knowledgeCard.entityCount", { count: evidence.graph.nodes.length }),
      t("knowledgeCard.relationCount", { count: evidence.graph.edges.length }),
      t("knowledgeCard.matchedCount", {
        count: evidence.graph.nodes.filter((node) => node.matched).length,
      })
    );
  } else if (evidence) {
    facts.push(
      t("knowledgeCard.chunkCount", { count: evidence.chunks.length }),
      t("knowledgeCard.documentCount", {
        count: groupSources(evidence.chunks).length,
      })
    );
  }
  const collections = evidence?.collections
    .map((collection) => collection.name)
    .filter(Boolean)
    .join(", ");
  if (collections) facts.push(collections);
  if (evidence?.elapsedMs !== null && evidence?.elapsedMs !== undefined) {
    facts.push(formatRunTime(evidence.elapsedMs));
  }

  return (
    <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
      <Text as="span" mainUiAction text04>
        {title}
      </Text>
      {facts.length > 0 && (
        <Text as="span" secondaryBody text03>
          {facts.join(" · ")}
        </Text>
      )}
    </span>
  );
}
