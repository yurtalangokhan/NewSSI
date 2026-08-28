import React from "react";
import { useTranslation } from "react-i18next";
import NumberInput from "./ConnectorInput/NumberInput";
import { TextFormField } from "@/components/Field";
import Button from "@/refresh-components/buttons/Button";
import { SvgTrash } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
export default function AdvancedFormPage() {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.advancedConnectorForm",
  });
  return (
    <div className="py-4 flex flex-col gap-y-6 rounded-lg max-w-2xl mx-auto">
      <Text as="h2" className="text-2xl font-bold mb-4 text-text-800">{t("title")}</Text>

      <NumberInput
        description={t("pruneFrequencyDescription")}
        label={t("pruneFrequencyLabel")}
        name="pruneFreq"
      />

      <NumberInput
        description={t("refreshFrequencyDescription")}
        label={t("refreshFrequencyLabel")}
        name="refreshFreq"
      />

      <TextFormField
        type="date"
        subtext={t("indexingStartDateSubtext")}
        optional
        label={t("indexingStartDateLabel")}
        name="indexingStart"
      />
      <div className="mt-4 flex w-full mx-auto max-w-2xl justify-start">
        <Button leftIcon={SvgTrash} danger type="submit">
          {t("resetButton")}
        </Button>
      </div>
    </div>
  );
}
