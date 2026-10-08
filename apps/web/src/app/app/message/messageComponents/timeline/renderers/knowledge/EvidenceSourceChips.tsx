import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import type { SourceGroup } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";

interface EvidenceSourceChipsProps {
  groups: SourceGroup[];
}

/** The documents the chunks came from, with a chunk count each. */
export function EvidenceSourceChips({ groups }: EvidenceSourceChipsProps) {
  const { t } = useTranslation();
  if (groups.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {groups.map((group) => (
        <span
          key={`${group.name}.${group.extension ?? ""}`}
          className="flex items-center gap-1.5 rounded-full border border-border-01 bg-background-neutral-00 py-0.5 pl-1 pr-2"
        >
          {group.extension && (
            <Text
              as="span"
              figureSmallValue
              className="rounded-full bg-background-tint-02 px-1.5"
            >
              {group.extension}
            </Text>
          )}
          <Text as="span" secondaryBody text04>
            {group.name} ·{" "}
            {t("knowledgeCard.chunkCount", { count: group.count })}
          </Text>
        </span>
      ))}
    </div>
  );
}
