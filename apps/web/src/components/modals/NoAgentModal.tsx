"use client";

import Modal from "@/refresh-components/Modal";
import { useTranslation } from "react-i18next";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { useUser } from "@/providers/UserProvider";
import { SvgUser } from "@opal/icons";

export default function NoAgentModal() {
  const { t } = useTranslation("modals");
  const { isAdmin } = useUser();

  return (
    <Modal open>
      <Modal.Content width="sm" height="sm">
        <Modal.Header icon={SvgUser} title={t("noAgent.title")} />
        <Modal.Body>
          <Text as="p">
            {t("noAgent.description")}
          </Text>
          {isAdmin ? (
            <>
              <Text as="p">
                {t("noAgent.adminDescription")}
              </Text>
              <Button className="w-full" href="/admin/agents">
                {t("noAgent.goToAdminPanel")}
              </Button>
            </>
          ) : (
            <Text as="p">
              {t("noAgent.contactAdmin")}
            </Text>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
