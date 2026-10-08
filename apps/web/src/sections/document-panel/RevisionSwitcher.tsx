"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgChevronLeft, SvgChevronRight, SvgUser } from "@/icons";
import type { RevisionSummary } from "@/lib/api/domains/documents/types";

interface RevisionSwitcherProps {
  revisions: RevisionSummary[];
  selected: number;
  onSelect: (revisionNo: number) => void;
}

export function RevisionSwitcher({
  revisions,
  selected,
  onSelect,
}: RevisionSwitcherProps) {
  const { t } = useTranslation();
  const numbers = revisions.map((r) => r.revision_no).sort((a, b) => a - b);
  const index = numbers.indexOf(selected);

  return (
    <div className="flex items-center gap-1" data-testid="revision-switcher">
      <Button
        icon={SvgChevronLeft}
        prominence="tertiary"
        size="sm"
        aria-label={t("documentPanel.previousDraft")}
        disabled={index <= 0}
        onClick={() => onSelect(numbers[index - 1]!)}
      />
      <div className="flex items-center gap-0.5 overflow-x-auto miniscroll">
        {numbers.map((no) => {
          const revision = revisions.find((r) => r.revision_no === no)!;
          return (
            <Button
              key={no}
              size="sm"
              variant="select"
              prominence="light"
              selected={no === selected}
              aria-pressed={no === selected}
              aria-label={t("documentPanel.draftLabel", { revision: no })}
              icon={revision.author_type === "user" ? SvgUser : undefined}
              onClick={() => onSelect(no)}
            >
              {t("documentPanel.draftPill", { revision: no })}
            </Button>
          );
        })}
      </div>
      <Button
        icon={SvgChevronRight}
        prominence="tertiary"
        size="sm"
        aria-label={t("documentPanel.nextDraft")}
        disabled={index === -1 || index >= numbers.length - 1}
        onClick={() => onSelect(numbers[index + 1]!)}
      />
    </div>
  );
}
