"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import type { IconFunctionComponent } from "@opal/types";
import { SvgFileText, SvgNetworkGraph } from "@opal/icons";
import { SvgLayers } from "@/icons/KnowledgeSearchIcons";
import {
  RETRIEVAL_KINDS,
  type RetrievalKind,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

const KIND_ICONS: Record<RetrievalKind, IconFunctionComponent> = {
  hybrid: SvgLayers,
  vector: SvgFileText,
  graph: SvgNetworkGraph,
};

interface RetrievalKindToggleProps {
  kind: RetrievalKind;
  onChange: (kind: RetrievalKind) => void;
  /** No graph search permission or no collection with a graph. */
  graphDisabled?: boolean;
}

/** Hybrid / Documents / Graph segmented control of the search box. */
export default function RetrievalKindToggle({
  kind,
  onChange,
  graphDisabled = false,
}: RetrievalKindToggleProps) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t("knowledgeSearch.kind.label")}
      className="flex shrink-0 items-center gap-0.5 rounded-12 bg-background-tint-02 p-0.5"
    >
      {RETRIEVAL_KINDS.map((option) => {
        const disabled = option === "graph" && graphDisabled;
        return (
          <Button
            key={option}
            icon={KIND_ICONS[option]}
            variant="select"
            selected={option === kind}
            aria-pressed={option === kind}
            size="md"
            disabled={disabled}
            tooltip={
              disabled
                ? t("knowledgeSearch.kind.graphUnavailable")
                : t(`knowledgeSearch.kind.${option}Hint`)
            }
            responsiveHideText
            onClick={() => onChange(option)}
          >
            {t(`knowledgeSearch.kind.${option}`)}
          </Button>
        );
      })}
    </div>
  );
}
