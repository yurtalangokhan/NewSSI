import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import { BlinkingBar } from "@/app/app/message/BlinkingBar";
import { EvidenceTextBlock } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceTextBlock";
import { DocumentEvidenceBody } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/DocumentEvidenceBody";
import { GraphEvidenceBody } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/GraphEvidenceBody";
import { KnowledgeCall } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/knowledgeCalls";

interface KnowledgeCallBodyProps {
  call: KnowledgeCall;
  compact?: boolean;
}

/** A knowledge call's content for its state: searching, evidence, or fallback. */
export function KnowledgeCallBody({
  call,
  compact = false,
}: KnowledgeCallBodyProps) {
  const { t } = useTranslation();

  if (call.status === "running") return <BlinkingBar />;
  if (call.status === "unavailable") {
    return (
      <Text as="p" secondaryBody text03>
        {t("knowledgeCard.unavailable")}
      </Text>
    );
  }
  if (call.evidence?.graph) {
    return <GraphEvidenceBody evidence={call.evidence} compact={compact} />;
  }
  if (call.evidence) {
    return <DocumentEvidenceBody evidence={call.evidence} compact={compact} />;
  }
  return (
    <EvidenceTextBlock className="max-h-96">
      {call.fallbackText ?? t("knowledgeCard.noResults")}
    </EvidenceTextBlock>
  );
}
