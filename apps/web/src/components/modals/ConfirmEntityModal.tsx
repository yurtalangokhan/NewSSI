import Modal from "@/refresh-components/layouts/ConfirmationModalLayout";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { SvgAlertCircle } from "@opal/icons";
import type { IconProps } from "@opal/types";
import { useTranslation } from "react-i18next";

export interface ConfirmEntityModalProps {
  danger?: boolean;

  onClose: () => void;
  onSubmit: () => void;

  icon?: React.FunctionComponent<IconProps>;

  entityType: string;
  entityName: string;

  additionalDetails?: string;

  action?: string;
  actionButtonText?: string;

  removeConfirmationText?: boolean;
}

export function ConfirmEntityModal({
  danger,

  onClose,
  onSubmit,

  icon: Icon,

  entityType,
  entityName,

  additionalDetails,

  action,
  actionButtonText,

  removeConfirmationText = false,
}: ConfirmEntityModalProps) {
  const { t } = useTranslation("modals");
  const buttonText = actionButtonText
    ? actionButtonText
    : danger
      ? t("delete")
      : t("confirm");
  const actionText =
    action ||
    (danger
      ? t("confirmEntity.deleteAction")
      : t("confirmEntity.modifyAction"));

  return (
    <Modal
      icon={Icon || SvgAlertCircle}
      title={`${buttonText} ${entityType}`}
      onClose={onClose}
      submit={
        <Button onClick={onSubmit} danger={danger}>
          {buttonText}
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        {!removeConfirmationText && (
          <Text as="p">
            {t("confirmEntity.confirmation", { action: actionText, entityName })}
          </Text>
        )}

        {additionalDetails && (
          <Text as="p" text03>
            {additionalDetails}
          </Text>
        )}
      </div>
    </Modal>
  );
}
