import { TextFormField } from "@/components/Field";
import { useTranslation } from "react-i18next";

interface SingleDefaultModelFieldProps {
  placeholder?: string;
}

export function SingleDefaultModelField({
  placeholder,
}: SingleDefaultModelFieldProps) {
  const { t } = useTranslation();

  return (
    <TextFormField
      name="default_model_name"
      label={t("llmConfig.defaultModelLabel")}
      subtext={t("llmConfig.defaultModelSubtext")}
      placeholder={placeholder ?? t("llmConfig.defaultModelPlaceholder")}
    />
  );
}
