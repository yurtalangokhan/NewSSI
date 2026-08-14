"use client";

import Modal from "@/refresh-components/Modal";
import { useTranslation } from "react-i18next";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { useUser } from "@/providers/UserProvider";
import { SvgUser } from "@opal/icons";

export default function NoAgentModal() {
  const { t } = useTranslation("common", { keyPrefix: "modals" });
  const { isAdmin } = useUser();

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
