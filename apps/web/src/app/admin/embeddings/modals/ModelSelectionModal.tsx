import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import { Callout } from "@/components/ui/callout";
import Button from "@/refresh-components/buttons/Button";
import { HostedEmbeddingModel } from "@/components/embedding/interfaces";
import { SvgServer } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface ModelSelectionConfirmationModalProps {
  selectedModel: HostedEmbeddingModel;
  isCustom: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ModelSelectionConfirmationModal({
  selectedModel,
  isCustom,
  onConfirm,
  onCancel,
}: ModelSelectionConfirmationModalProps) {
  const { t } = useTranslation();
  return (
    <Modal open onOpenChange={onCancel}>
      <Modal.Content width="sm" height="lg">
        <Modal.Header
          icon={SvgServer}
          title={t("admin.embeddings.updateModelTitle")}
          onClose={onCancel}
        />
        <Modal.Body>
          <Text as="p">
            {t("admin.embeddings.updateModelSelected")}{" "}
            <strong>{selectedModel.model_name}</strong>.{" "}
            {t("admin.embeddings.updateModelConfirm")}
          </Text>
          <Text as="p">{t("admin.embeddings.updateModelBody")}</Text>
          <Text as="p">
            <i>{t("admin.embeddings.noteLabel")}</i>{" "}
            {t("admin.embeddings.updateModelNote")}
          </Text>

          {isCustom && (
            <Callout
              type="warning"
              title={t("admin.embeddings.importantTitle")}
            >
              {t("admin.embeddings.customModelWarning1")}{" "}
              <strong>{t("admin.embeddings.afterLabel")}</strong>{" "}
              {t("admin.embeddings.customModelWarning2")}
            </Callout>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={onConfirm}>
            {t("admin.embeddings.confirmButton")}
          </Button>
          <Button secondary onClick={onCancel}>
            {t("admin.embeddings.cancelButton")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
