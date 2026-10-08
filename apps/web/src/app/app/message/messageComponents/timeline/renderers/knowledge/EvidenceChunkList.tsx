import type { EvidenceChunk } from "@/lib/api/domains/chat/knowledge-evidence-types";
import { EvidenceChunkRow } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceChunkRow";

interface EvidenceChunkListProps {
  chunks: readonly EvidenceChunk[];
  query: string;
  selectedRef: number | null;
  compact?: boolean;
  onOpen: (chunk: EvidenceChunk) => void;
}

export function EvidenceChunkList({
  chunks,
  query,
  selectedRef,
  compact,
  onOpen,
}: EvidenceChunkListProps) {
  return (
    <ol className="flex flex-col gap-2">
      {chunks.map((chunk) => (
        <li key={chunk.ref}>
          <EvidenceChunkRow
            chunk={chunk}
            query={query}
            selected={chunk.ref === selectedRef}
            compact={compact}
            onOpen={onOpen}
          />
        </li>
      ))}
    </ol>
  );
}
