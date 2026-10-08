"use client";

import { useTranslation } from "react-i18next";
import { useScoreFormatter } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/useScoreFormatter";
import Text from "@/refresh-components/texts/Text";

interface RelevanceMeterProps {
  /** Relevance relative to the best hit, 0–1. */
  value: number;
}

/** A hit's relative relevance as a number and a bar on the same scale. */
export default function RelevanceMeter({ value }: RelevanceMeterProps) {
  const { t } = useTranslation();
  const formatScore = useScoreFormatter();
  const ratio = Math.min(1, Math.max(0, value));
  const formatted = formatScore(ratio);
  return (
    <span
      role="meter"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={ratio}
      aria-valuetext={formatted}
      className="flex shrink-0 items-center gap-2"
      aria-label={t("knowledgeSearch.hit.relevance", { value: formatted })}
      title={t("knowledgeSearch.hit.relevance", { value: formatted })}
    >
      <Text as="span" secondaryMono text03 className="tabular-nums" aria-hidden>
        {formatted}
      </Text>
      <span
        className="hidden h-1 w-11 overflow-hidden rounded-full bg-background-tint-03 sm:block"
        aria-hidden
      >
        <span
          className="block h-full rounded-full bg-text-04"
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </span>
    </span>
  );
}
