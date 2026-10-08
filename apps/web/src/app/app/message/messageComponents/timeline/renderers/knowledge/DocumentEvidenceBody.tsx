import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import type { KnowledgeEvidence } from "@/lib/api/domains/chat/knowledge-evidence-types";
import { groupSources } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";
import { EvidenceChunkList } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceChunkList";
import { EvidenceChunkPanel } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceChunkPanel";
import { EvidenceQueryLine } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceQueryLine";
import { EvidenceSourceChips } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceSourceChips";
import { ModelContextDisclosure } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/ModelContextDisclosure";

interface DocumentEvidenceBodyProps {
  evidence: KnowledgeEvidence;
  /** Narrow surfaces (the flow node drawer) show a denser list. */
  compact?: boolean;
}

/** The chunks a document search used; opening one shows its full text. */
export function DocumentEvidenceBody({
  evidence,
  compact = false,
}: DocumentEvidenceBodyProps) {
  const { t } = useTranslation();
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const sources = useMemo(
    () => groupSources(evidence.chunks),
    [evidence.chunks]
  );
  const selectedRef =
    openIndex !== null ? evidence.chunks[openIndex]?.ref ?? null : null;

  return (
    <div className="flex flex-col gap-3">
      <EvidenceQueryLine evidence={evidence} />
      {!compact && <EvidenceSourceChips groups={sources} />}
      {evidence.chunks.length > 0 ? (
        <EvidenceChunkList
          chunks={evidence.chunks}
          query={evidence.query}
          selectedRef={selectedRef}
          compact={compact}
          onOpen={(chunk) => setOpenIndex(evidence.chunks.indexOf(chunk))}
        />
      ) : (
        <Text as="p" secondaryBody text03>
          {t("knowledgeCard.noResults")}
        </Text>
      )}
      {!compact && (
        <div className="flex flex-col gap-2">
          {evidence.chunks.length > 0 && (
            <Text as="p" secondaryBody text03>
              {t("knowledgeCard.rankingHint")}
            </Text>
          )}
          <ModelContextDisclosure
            context={evidence.modelContext}
            truncated={evidence.modelContextTruncated}
          />
        </div>
      )}
      <EvidenceChunkPanel
        chunks={evidence.chunks}
        openIndex={openIndex}
        query={evidence.query}
        collections={evidence.collections}
        searchMode={t("knowledgeCard.modeDocument")}
        onIndexChange={setOpenIndex}
      />
    </div>
  );
}
