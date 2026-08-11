import { SvgOrganization } from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface Props {
  organizationName: string;
  currentParentName: string;
  newParentName: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function OrganizationMoveConfirmationModal({
  organizationName,
  currentParentName,
  newParentName,
  onCancel,
  onConfirm,
}: Props) {
  const { t } = useTranslation();
  return (
    <ConfirmationModalLayout
      icon={SvgOrganization}
      title={t("admin.organizations.moveConfirm.title")}
      onClose={onCancel}
      submit={
        <Button action primary onClick={onConfirm}>
          {t("admin.organizations.moveConfirm.confirm")}
        </Button>
      }
    >
      <div className={cn("flex flex-col gap-3")}>
        <Text mainUiBody text04>
          {t("admin.organizations.moveConfirm.description", {
            name: organizationName,
          })}
        </Text>
        <div className={cn("rounded-08 bg-background-neutral-02 p-3")}>
          <Text secondaryBody text03 as="p">
            {currentParentName}
          </Text>
          <Text mainUiAction text05 as="p">
            → {newParentName}
          </Text>
        </div>
      </div>
    </ConfirmationModalLayout>
  );
}
