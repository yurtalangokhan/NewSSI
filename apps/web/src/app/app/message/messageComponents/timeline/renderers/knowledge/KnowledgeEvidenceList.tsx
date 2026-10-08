import type { KnowledgeEvidence } from "@/lib/api/domains/chat/knowledge-evidence-types";
import { KnowledgeCallBody } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/KnowledgeCallBody";
import { KnowledgeCallHeader } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/KnowledgeCallHeader";
import type { KnowledgeCall } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/knowledgeCalls";

interface KnowledgeEvidenceListProps {
  evidence: readonly KnowledgeEvidence[];
}

function asCall(evidence: KnowledgeEvidence): KnowledgeCall {
  return {
    callId: null,
    toolName: evidence.tool,
    query: evidence.query,
    status: "done",
    evidence,
    fallbackText: null,
  };
}

/** Compact evidence cards for narrow surfaces such as the flow node drawer. */
export function KnowledgeEvidenceList({
  evidence,
}: KnowledgeEvidenceListProps) {
  return (
    <div className="flex flex-col gap-4">
      {evidence.map((item, index) => {
        const call = asCall(item);
        return (
          <section
            key={`${item.tool}-${index}`}
            className="flex flex-col gap-2"
          >
            <KnowledgeCallHeader call={call} />
            <KnowledgeCallBody call={call} compact />
          </section>
        );
      })}
    </div>
  );
}
