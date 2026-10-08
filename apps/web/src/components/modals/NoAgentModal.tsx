"use client";

import { useState } from "react";
import Modal from "@/refresh-components/Modal";
import { useTranslation } from "react-i18next";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { useUser } from "@/providers/UserProvider";
import { SvgUser } from "@opal/icons";

interface NoAgentModalProps {
  catalogError?: boolean;
  onRetry?: () => Promise<void>;
}

export default function NoAgentModal({
  catalogError = false,
  onRetry,
}: NoAgentModalProps) {
  const { t } = useTranslation("common", { keyPrefix: "modals" });
  const { isAdmin } = useUser();
  const [retrying, setRetrying] = useState(false);

  async function retry() {
    setRetrying(true);
    try {
      await onRetry?.();
    } catch {
      // SWR retains the request error; keep the retry action available.
    } finally {
      setRetrying(false);
    }
  }

  if (catalogError) {
    return (
      <Modal open>
        <Modal.Content width="sm" height="sm">
          <Modal.Header icon={SvgUser} title={t("noAgent.loadErrorTitle")} />
          <Modal.Body>
            <Text as="p">{t("noAgent.loadErrorMessage")}</Text>
            <Button className="w-full" disabled={retrying} onClick={retry}>
              {t("noAgent.retry")}
            </Button>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    );
  }

  return (
    <Modal open>
      <Modal.Content width="sm" height="sm">
        <Modal.Header icon={SvgUser} title={t("noAgent.title")} />
        <Modal.Body>
          <Text as="p">{t("noAgent.noAgentConfiguredMessage")}</Text>
          {isAdmin ? (
            <>
              <Text as="p">{t("noAgent.adminCreateAgentMessage")}</Text>
              <Button className="w-full" href="/admin/agents">
                {t("noAgent.goToAdminPanel")}
              </Button>
            </>
          ) : (
            <Text as="p">{t("noAgent.contactAdminMessage")}</Text>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
