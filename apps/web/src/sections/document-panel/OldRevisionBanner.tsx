"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgHistory } from "@/icons";
import Text from "@/refresh-components/texts/Text";

interface OldRevisionBannerProps {
  onContinue: () => void;
  onGoToLatest: () => void;
  busy: boolean;
}

export function OldRevisionBanner({
  onContinue,
  onGoToLatest,
  busy,
}: OldRevisionBannerProps) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className="flex items-center gap-2 px-3 py-2 bg-status-warning-01 border-b border-border-01"
    >
      <SvgHistory size={14} className="text-text-03" />
      <Text as="p" secondaryBody text04 className="flex-1">
        {t("documentPanel.oldRevision.message")}
      </Text>
      <Button prominence="tertiary" size="sm" onClick={onGoToLatest}>
        {t("documentPanel.oldRevision.goToLatest")}
      </Button>
      <Button
        prominence="secondary"
        size="sm"
        onClick={onContinue}
        disabled={busy}
      >
        {t("documentPanel.oldRevision.continue")}
      </Button>
    </div>
  );
}
