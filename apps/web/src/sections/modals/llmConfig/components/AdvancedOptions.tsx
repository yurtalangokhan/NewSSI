import { FormikProps } from "formik";
import { AdvancedOptionsToggle } from "@/components/AdvancedOptionsToggle";
import { IsPublicGroupSelector } from "@/components/IsPublicGroupSelector";
import { AgentsMultiSelect } from "@/components/AgentsMultiSelect";
import Text from "@/refresh-components/texts/Text";
import { useState } from "react";
import { useAgents } from "@/hooks/useAgents";
import { useTranslation } from "react-i18next";

export function AdvancedOptions({
  formikProps,
}: {
  formikProps: FormikProps<any>;
}) {
  const { agents, isLoading: agentsLoading, error: agentsError } = useAgents();
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const { t } = useTranslation();

  return (
    <>
      <AdvancedOptionsToggle
        showAdvancedOptions={showAdvancedOptions}
        setShowAdvancedOptions={setShowAdvancedOptions}
      />

      {showAdvancedOptions && (
        <>
          <div className="flex flex-col gap-3">
            <Text as="p" headingH3>
              {t("llmConfig.accessControls")}
            </Text>
            <IsPublicGroupSelector
              formikProps={formikProps}
              objectName={t("llmConfig.llmProviderObjectName")}
              publicToWhom="Users"
              enforceGroupSelection={true}
              smallLabels={true}
            />
            <AgentsMultiSelect
              formikProps={formikProps}
              agents={agents}
              isLoading={agentsLoading}
              error={agentsError}
              label={t("llmConfig.agentWhitelistLabel")}
              subtext={t("llmConfig.agentWhitelistSubtext")}
              disabled={formikProps.values.is_public}
              disabledMessage={t("llmConfig.agentWhitelistDisabled")}
            />
          </div>
        </>
      )}
    </>
  );
}
