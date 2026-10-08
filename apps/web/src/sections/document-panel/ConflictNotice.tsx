"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgAlertTriangle } from "@/icons";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Text from "@/refresh-components/texts/Text";

interface ConflictNoticeProps {
  baseRevisionNo: number;
  headRevisionNo: number;
  /** The edit started from a draft that was already older than the head. */
  staleAtStart?: boolean;
  onApplyOnLatest: () => void;
  onOverwrite: () => void;
  onShowDiff: () => void;
  busy: boolean;
}

export function ConflictNotice({
  baseRevisionNo,
  headRevisionNo,
  staleAtStart = false,
  onApplyOnLatest,
  onOverwrite,
  onShowDiff,
  busy,
}: ConflictNoticeProps) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-12 border border-border-02 bg-status-warning-01 p-3"
    >
      <div className="flex items-start gap-2">
        <SvgAlertTriangle size={16} className="text-text-04 mt-0.5" />
        <Text as="p" secondaryBody text05>
          {t(
            staleAtStart
              ? "documentPanel.conflict.staleMessage"
              : "documentPanel.conflict.message",
            { head: headRevisionNo, base: baseRevisionNo }
          )}
        </Text>
      </div>
      <div className="flex flex-wrap gap-1">
        <Button
          size="sm"
          prominence="primary"
          disabled={busy}
          onClick={onApplyOnLatest}
        >
          {t("documentPanel.conflict.applyOnLatest", { head: headRevisionNo })}
        </Button>
        <Button
          size="sm"
          prominence="secondary"
          disabled={busy}
          onClick={() => setConfirming(true)}
        >
          {t("documentPanel.conflict.overwrite")}
        </Button>
        <Button size="sm" prominence="tertiary" onClick={onShowDiff}>
          {t("documentPanel.conflict.showDiff")}
        </Button>
      </div>
      {confirming && (
        <ConfirmationModalLayout
          icon={SvgAlertTriangle}
          title={t("documentPanel.conflict.overwriteConfirm.title", {
            head: headRevisionNo,
          })}
          onClose={() => setConfirming(false)}
          submit={
            <Button
              variant="danger"
              onClick={() => {
                setConfirming(false);
                onOverwrite();
              }}
            >
              {t("documentPanel.conflict.overwriteConfirm.confirm")}
            </Button>
          }
        >
          {t("documentPanel.conflict.overwriteConfirm.body", {
            head: headRevisionNo,
          })}
        </ConfirmationModalLayout>
      )}
    </div>
  );
}
