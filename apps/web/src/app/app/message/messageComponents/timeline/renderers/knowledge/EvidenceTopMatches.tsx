import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import Text from "@/refresh-components/texts/Text";
import type { EvidenceGraphNode } from "@/lib/api/domains/chat/knowledge-evidence-types";
import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";

interface EvidenceTopMatchesProps {
  /** Direct matches, strongest first. */
  matches: readonly EvidenceGraphNode[];
  focusedId: string | null;
  onSelect: (nodeId: string) => void;
}

/** The entities the query matched, in RRF rank order: the search's answer. */
export function EvidenceTopMatches({
  matches,
  focusedId,
  onSelect,
}: EvidenceTopMatchesProps) {
  const { t } = useTranslation();
  const title = t("knowledgeCard.topMatches");

  return (
    <section className="flex min-w-0 flex-col gap-2 rounded-08 border border-border-01 bg-background-neutral-00 p-3">
      <Text as="h3" secondaryAction text05>
        {title}
      </Text>
      <ol
        aria-label={title}
        className="flex max-h-64 flex-col gap-0.5 overflow-y-auto"
      >
        {matches.map((node, index) => {
          const pressed = node.id === focusedId;
          return (
            <li key={node.id}>
              <Interactive.Base
                variant="select"
                prominence="heavy"
                selected={pressed}
                onClick={() => onSelect(node.id)}
              >
                <Interactive.Container
                  type="button"
                  aria-pressed={pressed}
                  heightVariant="fit"
                  widthVariant="full"
                  roundingVariant="compact"
                >
                  <span className="flex min-w-0 items-center gap-2 px-2 py-1.5 text-left">
                    <Text
                      as="span"
                      secondaryBody
                      text02
                      className="w-4 shrink-0 text-right tabular-nums"
                    >
                      {index + 1}
                    </Text>
                    <span
                      aria-hidden
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{
                        background: entityColorVar(
                          entityColor(node.label),
                          "05"
                        ),
                      }}
                    />
                    <Text as="span" secondaryBody text05 className="truncate">
                      {node.name}
                    </Text>
                    <Text
                      as="span"
                      secondaryBody
                      text03
                      className="ml-auto shrink-0"
                    >
                      {node.label}
                    </Text>
                  </span>
                </Interactive.Container>
              </Interactive.Base>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
