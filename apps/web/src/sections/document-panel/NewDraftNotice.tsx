"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgSparkle } from "@/icons";
import Text from "@/refresh-components/texts/Text";

interface NewDraftNoticeProps {
  revisionNo: number;
  onView: () => void;
}

export function NewDraftNotice({ revisionNo, onView }: NewDraftNoticeProps) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 px-3 py-2 bg-status-info-01 border-b border-border-01"
    >
      <SvgSparkle size={14} className="text-text-03" />
      <Text as="p" secondaryBody text04 className="flex-1">
        {t("documentPanel.newDraft.message", { revision: revisionNo })}
      </Text>
      <Button prominence="secondary" size="sm" onClick={onView}>
        {t("documentPanel.newDraft.view")}
      </Button>
    </div>
  );
}
