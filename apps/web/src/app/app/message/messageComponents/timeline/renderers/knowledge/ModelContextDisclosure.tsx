import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { EvidenceTextBlock } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceTextBlock";

interface ModelContextDisclosureProps {
  context: string;
  truncated: boolean;
}

/** The exact text the model received, behind a toggle. */
export function ModelContextDisclosure({
  context,
  truncated,
}: ModelContextDisclosureProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (!context) return null;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <Button
          variant="action"
          prominence="tertiary"
          size="sm"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open
            ? t("knowledgeCard.hideModelContext")
            : t("knowledgeCard.showModelContext")}
        </Button>
      </div>
      {open && (
        <div className="flex flex-col gap-1">
          <EvidenceTextBlock className="max-h-56">{context}</EvidenceTextBlock>
          {truncated && (
            <Text as="p" secondaryBody text03>
              {t("knowledgeCard.modelContextTruncated")}
            </Text>
          )}
        </div>
      )}
    </div>
  );
}
