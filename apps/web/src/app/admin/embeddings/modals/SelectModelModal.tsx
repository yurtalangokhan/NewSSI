import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { CloudEmbeddingModel } from "@/components/embedding/interfaces";
import { SvgServer } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface SelectModelModalProps {
  model: CloudEmbeddingModel;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function SelectModelModal({
  model,
  onConfirm,
  onCancel,
}: SelectModelModalProps) {
  const { t } = useTranslation();
  return (
    <Modal open onOpenChange={onCancel}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgServer}
          title={t("admin.embeddings.selectModelTitle", {
            modelName: model.model_name,
          })}
          onClose={onCancel}
        />
        <Modal.Body>
          <Text as="p">
            {t("admin.embeddings.selectModelBody1")}{" "}
            <strong>{model.model_name}</strong>.{" "}
            {t("admin.embeddings.selectModelBody2")}
          </Text>
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
