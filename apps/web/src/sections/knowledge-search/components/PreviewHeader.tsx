"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgX } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";

interface PreviewHeaderProps {
  marker: React.ReactNode;
  title: string;
  tags: React.ReactNode;
  actions: React.ReactNode;
  onClose: () => void;
}

/** Title row, tags, and actions of a result preview. */
export default function PreviewHeader({
  marker,
  title,
  tags,
  actions,
  onClose,
}: PreviewHeaderProps) {
  const { t } = useTranslation();
  return (
    <header className="flex flex-col gap-2.5 border-b border-border-01 px-4 py-4">
      <div className="flex items-start gap-2.5">
        {marker}
        <Text as="h2" headingH3 text05 className="min-w-0 flex-1 break-words">
          {title}
        </Text>
        <Button
          icon={SvgX}
          prominence="tertiary"
          size="md"
          tooltip={t("knowledgeSearch.preview.close")}
          aria-label={t("knowledgeSearch.preview.close")}
          onClick={onClose}
        />
      </div>
      <div className="flex flex-wrap items-center gap-1.5">{tags}</div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </header>
  );
}
