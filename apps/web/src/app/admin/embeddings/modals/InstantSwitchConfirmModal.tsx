import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { SvgAlertTriangle } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface InstantSwitchConfirmModalProps {
  onClose: () => void;
  onConfirm: () => void;
}

export default function InstantSwitchConfirmModal({
  onClose,
  onConfirm,
}: InstantSwitchConfirmModalProps) {
  const { t } = useTranslation();

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgAlertTriangle}
          title={t("admin.embeddings.instantSwitchTitle")}
          onClose={onClose}
        />
        <Modal.Body>
          <Text as="p">{t("admin.embeddings.instantSwitchBody")}</Text>
          <Text as="p">
            <strong>{t("admin.embeddings.instantSwitchIrreversible")}</strong>
          </Text>
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={onConfirm}>
            {t("admin.embeddings.confirmButton")}
          </Button>
          <Button secondary onClick={onClose}>
            {t("admin.embeddings.cancelButton")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
