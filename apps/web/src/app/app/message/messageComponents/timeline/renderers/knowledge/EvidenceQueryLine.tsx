import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import type { KnowledgeEvidence } from "@/lib/api/domains/chat/knowledge-evidence-types";

interface EvidenceQueryLineProps {
  evidence: KnowledgeEvidence;
}

interface FactProps {
  label: string;
  value: string;
}

function Fact({ label, value }: FactProps) {
  return (
    <Text as="span" secondaryBody text03>
      {label}{" "}
      <Text as="span" secondaryAction text05>
        {value}
      </Text>
    </Text>
  );
}

/** What was searched: the query, the collections, and the search mode. */
export function EvidenceQueryLine({ evidence }: EvidenceQueryLineProps) {
  const { t } = useTranslation();
  const collections = evidence.collections
    .map((collection) => collection.name ?? collection.id)
    .join(", ");
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      <Fact
        label={t("knowledgeCard.queryLabel")}
        value={`“${evidence.query}”`}
      />
      {collections && (
        <Fact label={t("knowledgeCard.collectionLabel")} value={collections} />
      )}
      <Fact
        label={t("knowledgeCard.modeLabel")}
        value={
          evidence.kind === "graph"
            ? t("knowledgeCard.modeGraph")
            : t("knowledgeCard.modeDocument")
        }
      />
    </div>
  );
}
