import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import type { EvidenceChunk } from "@/lib/api/domains/chat/knowledge-evidence-types";
import { documentDisplay } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";
import { EvidenceScore } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceScore";
import { HighlightedText } from "@/refresh-components/texts/HighlightedText";

interface EvidenceChunkRowProps {
  chunk: EvidenceChunk;
  query: string;
  selected: boolean;
  compact?: boolean;
  onOpen: (chunk: EvidenceChunk) => void;
}

/** One ranked chunk: rank, source, a highlighted preview, and its score. */
export function EvidenceChunkRow({
  chunk,
  query,
  selected,
  compact = false,
  onOpen,
}: EvidenceChunkRowProps) {
  const { t } = useTranslation();
  const { name } = documentDisplay(chunk.source);
  const location = [
    chunk.source.page !== null
      ? t("knowledgeCard.pageShort", { page: chunk.source.page })
      : null,
    chunk.source.section,
  ].filter(Boolean);

  return (
    <Interactive.Base
      variant="select"
      prominence="heavy"
      selected={selected}
      onClick={() => onOpen(chunk)}
    >
      <Interactive.Container
        type="button"
        border
        heightVariant="fit"
        widthVariant="full"
        roundingVariant="compact"
        aria-haspopup="dialog"
        aria-pressed={selected}
      >
        <span
          className={cn(
            "grid w-full grid-cols-[1.5rem_minmax(0,1fr)_auto] items-start gap-x-3 text-left",
            compact ? "px-2.5 py-2" : "px-3 py-2.5"
          )}
        >
          <Text
            as="span"
            secondaryMono
            text04
            className="flex h-6 w-6 items-center justify-center rounded-04 border border-border-01 bg-background-tint-01"
          >
            {chunk.ref}
          </Text>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="flex flex-wrap items-center gap-x-1.5">
              {name && (
                <Text as="span" secondaryAction text05>
                  {name}
                </Text>
              )}
              {location.map((part) => (
                <Text key={part} as="span" secondaryBody text03>
                  · {part}
                </Text>
              ))}
            </span>
            <Text
              as="span"
              secondaryBody
              text04
              className={cn(compact ? "line-clamp-1" : "line-clamp-2")}
            >
              <HighlightedText text={chunk.content} query={query} />
            </Text>
          </span>
          <EvidenceScore score={chunk.score} />
        </span>
      </Interactive.Container>
    </Interactive.Base>
  );
}
