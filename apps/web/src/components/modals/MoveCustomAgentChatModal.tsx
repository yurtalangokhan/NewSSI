"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import Text from "@/refresh-components/texts/Text";
import { SvgAlertCircle } from "@opal/icons";
interface MoveCustomAgentChatModalProps {
  onCancel: () => void;
  onConfirm: (doNotShowAgain: boolean) => void;
}

export default function MoveCustomAgentChatModal({
  onCancel,
  onConfirm,
}: MoveCustomAgentChatModalProps) {
  const { t } = useTranslation();
  const [doNotShowAgain, setDoNotShowAgain] = useState(false);

  return (
    <ConfirmationModalLayout
      icon={SvgAlertCircle}
      title={t("modals.moveCustomAgentChat.title")}
      onClose={onCancel}
      submit={
        <Button primary onClick={() => onConfirm(doNotShowAgain)}>
          {t("modals.moveCustomAgentChat.confirmButton")}
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <Text as="p" text03>
          {t("modals.moveCustomAgentChat.warning")}
        </Text>
        <div className="flex items-center gap-1">
          <Checkbox
            id="move-custom-agent-do-not-show"
            checked={doNotShowAgain}
            onCheckedChange={(checked) => setDoNotShowAgain(Boolean(checked))}
          />
          <label
            htmlFor="move-custom-agent-do-not-show"
            className="text-text-03 text-sm"
          >
            {t("modals.moveCustomAgentChat.doNotShowAgain")}
          </label>
        </div>
      </div>
    </ConfirmationModalLayout>
  );
}
