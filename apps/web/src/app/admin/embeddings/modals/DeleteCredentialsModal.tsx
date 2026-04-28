import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import Button from "@/refresh-components/buttons/Button";
import { Callout } from "@/components/ui/callout";
import {
  CloudEmbeddingProvider,
  getFormattedProviderName,
} from "../../../../components/embedding/interfaces";
import { SvgTrash } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface DeleteCredentialsModalProps {
  modelProvider: CloudEmbeddingProvider;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function DeleteCredentialsModal({
  modelProvider,
  onConfirm,
  onCancel,
}: DeleteCredentialsModalProps) {
  const { t } = useTranslation();
  return (
    <Modal open onOpenChange={onCancel}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgTrash}
          title={t("admin.embeddings.deleteCredentialsTitle", {
            provider: getFormattedProviderName(modelProvider.provider_type),
          })}
          onClose={onCancel}
        />
        <Modal.Body>
          <Text as="p">
            {t("admin.embeddings.deleteCredentialsBody", {
              provider: getFormattedProviderName(modelProvider.provider_type),
            })}
          </Text>
          <Callout type="danger" title={t("admin.embeddings.pointOfNoReturn")} />
        </Modal.Body>
        <Modal.Footer>
          <Button secondary onClick={onCancel}>
            {t("admin.embeddings.keepCredentials")}
          </Button>
          <Button danger onClick={onConfirm}>
            {t("admin.embeddings.deleteCredentials")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
