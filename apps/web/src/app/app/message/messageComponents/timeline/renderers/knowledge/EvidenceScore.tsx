import Text from "@/refresh-components/texts/Text";
import { scoreRatio } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";
import { useScoreFormatter } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/useScoreFormatter";

interface EvidenceScoreProps {
  score: number | null;
}

/** A similarity score as a number and a bar on the same 0..1 scale. */
export function EvidenceScore({ score }: EvidenceScoreProps) {
  const formatScore = useScoreFormatter();
  if (score === null) return null;
  return (
    <span className="flex flex-col items-end gap-1">
      <Text as="span" secondaryMono text05 className="tabular-nums">
        {formatScore(score)}
      </Text>
      <span className="block h-1 w-16 rounded-full bg-border-01" aria-hidden>
        <span
          className="block h-full rounded-full bg-action-link-05"
          style={{ width: `${Math.round(scoreRatio(score) * 100)}%` }}
        />
      </span>
    </span>
  );
}
