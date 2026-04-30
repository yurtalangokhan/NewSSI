import { TextFormField } from "@/components/Field";
import { useTranslation } from "react-i18next";

interface DisplayNameFieldProps {
  disabled?: boolean;
}

export function DisplayNameField({ disabled = false }: DisplayNameFieldProps) {
  const { t } = useTranslation();
  return (
    <TextFormField
      name="name"
      label={t("llmConfig.displayNameLabel")}
      subtext={t("llmConfig.displayNameSubtext")}
      placeholder={t("llmConfig.displayNamePlaceholder")}
      disabled={disabled}
    />
  );
}
