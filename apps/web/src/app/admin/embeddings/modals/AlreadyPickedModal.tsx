import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import { CloudEmbeddingModel } from "../../../../components/embedding/interfaces";
import { SvgCheck } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface AlreadyPickedModalProps {
  model: CloudEmbeddingModel;
  onClose: () => void;
}

export default function AlreadyPickedModal({
  model,
  onClose,
}: AlreadyPickedModalProps) {
  const { t } = useTranslation("admin");
  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgCheck}
          title={t("embeddings.alreadyChosenTitle", { modelName: model.model_name })}
          description={t("embeddings.alreadyChosenDescription")}
          onClose={onClose}
        />
        <Modal.Footer>
          <Button onClick={onClose}>{t("embeddings.closeButton")}</Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
