import React, { useMemo } from "react";
import * as Yup from "yup";
import { Trans, useTranslation } from "react-i18next";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import InputComboBox from "@/refresh-components/inputs/InputComboBox";
import Separator from "@/refresh-components/Separator";
import { Button } from "@opal/components";
import { cn, noProp } from "@/lib/utils";
import { SvgRefreshCw } from "@opal/icons";
import { WellKnownLLMProviderDescriptor } from "@/interfaces/llm";
import {
  OnboardingFormWrapper,
  OnboardingFormChildProps,
} from "./OnboardingFormWrapper";
import { OnboardingActions, OnboardingState } from "../types";
import { buildInitialValues } from "../components/llmConnectionHelpers";
import ConnectionProviderIcon from "@/refresh-components/ConnectionProviderIcon";
import InlineExternalLink from "@/refresh-components/InlineExternalLink";
import { ProviderIcon } from "@/app/admin/configuration/llm/ProviderIcon";

// Field name constants
const FIELD_API_KEY = "api_key";
const FIELD_DEFAULT_MODEL_NAME = "default_model_name";

interface OpenRouterOnboardingFormProps {
  llmDescriptor: WellKnownLLMProviderDescriptor;
  onboardingState: OnboardingState;
  onboardingActions: OnboardingActions;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface OpenRouterFormValues {
  name: string;
  provider: string;
  api_key: string;
  api_base: string;
  api_key_changed: boolean;
  default_model_name: string;
  model_configurations: any[];
  groups: number[];
  is_public: boolean;
}

function OpenRouterFormFields(
  props: OnboardingFormChildProps<OpenRouterFormValues>
) {
  const {
    formikProps,
    apiStatus,
    showApiMessage,
    errorMessage,
    modelOptions,
    isFetchingModels,
    handleFetchModels,
    modelsApiStatus,
    modelsErrorMessage,
    showModelsApiErrorMessage,
    disabled,
  } = props;
  const { t } = useTranslation();

  const handleApiKeyInteraction = () => {
    if (formikProps.values.api_key) {
      handleFetchModels();
    }
  };

  return (
    <>
      <FormikField<string>
        name={FIELD_API_KEY}
        render={(field, helper, meta, state) => (
          <FormField name={FIELD_API_KEY} state={state} className="w-full">
            <FormField.Label>{t("llmOnboarding.apiKey")}</FormField.Label>
            <FormField.Control>
              <PasswordInputTypeIn
                {...field}
                placeholder=""
                error={apiStatus === "error"}
                showClearButton={false}
                disabled={disabled}
                onBlur={(e) => {
                  field.onBlur(e);
                  handleApiKeyInteraction();
                }}
              />
            </FormField.Control>
            {!showApiMessage && (
              <FormField.Message
                messages={{
                  idle: (
                    <Trans
                      i18nKey="llmOnboarding.pasteApiKeyHint"
                      values={{ provider: "OpenRouter" }}
                      components={{
                        link: (
                          <InlineExternalLink href="https://openrouter.ai/settings/keys">
                            API key
                          </InlineExternalLink>
                        ),
                      }}
                    />
                  ),
                  error: meta.error,
                }}
              />
            )}
            {showApiMessage && (
              <FormField.APIMessage
                state={apiStatus}
                messages={{
                  loading: t("llmOnboarding.checkingOpenRouter"),
                  success: t("llmOnboarding.openRouterValid"),
                  error: errorMessage || t("llmOnboarding.invalidApiKey"),
                }}
              />
            )}
          </FormField>
        )}
      />

      <Separator className="py-0" />

      <FormikField<string>
        name={FIELD_DEFAULT_MODEL_NAME}
        render={(field, helper, meta, state) => (
          <FormField
            name={FIELD_DEFAULT_MODEL_NAME}
            state={state}
            className="w-full"
          >
            <FormField.Label>{t("llmOnboarding.defaultModel")}</FormField.Label>
            <FormField.Control>
              <InputComboBox
                value={field.value}
                onValueChange={(value) => helper.setValue(value)}
                onChange={(e) => helper.setValue(e.target.value)}
                options={modelOptions}
                disabled={
                  disabled || isFetchingModels || modelOptions.length === 0
                }
                rightSection={
                  <Button
                    prominence="tertiary"
                    size="sm"
                    icon={({ className }) => (
                      <SvgRefreshCw
                        className={cn(
                          className,
                          isFetchingModels && "animate-spin"
                        )}
                      />
                    )}
                    onClick={noProp((e) => {
                      e.preventDefault();
                      handleFetchModels();
                    })}
                    tooltip={t("llmOnboarding.fetchAvailableModels")}
                    disabled={disabled || isFetchingModels}
                  />
                }
                onBlur={field.onBlur}
                placeholder={t("llmOnboarding.selectOrTypeModel")}
              />
            </FormField.Control>
            {!showModelsApiErrorMessage && (
              <FormField.Message
                messages={{
                  idle: t("llmOnboarding.defaultModelDesc"),
                  error: meta.error,
                }}
              />
            )}
            {showModelsApiErrorMessage && (
              <FormField.APIMessage
                state={modelsApiStatus}
                messages={{
                  loading: t("llmOnboarding.fetchingModels"),
                  success: t("llmOnboarding.modelsFetched"),
                  error: modelsErrorMessage || t("llmOnboarding.failedFetchModels"),
                }}
              />
            )}
          </FormField>
        )}
      />
    </>
  );
}

export function OpenRouterOnboardingForm({
  llmDescriptor,
  onboardingState,
  onboardingActions,
  open,
  onOpenChange,
}: OpenRouterOnboardingFormProps) {
  const { t } = useTranslation();
  const initialValues = useMemo(
    (): OpenRouterFormValues => ({
      ...buildInitialValues(),
      name: llmDescriptor.name,
      provider: llmDescriptor.name,
      api_base: "https://openrouter.ai/api/v1",
    }),
    [llmDescriptor.name]
  );

  const validationSchema = Yup.object().shape({
    [FIELD_API_KEY]: Yup.string().required(t("llmOnboardingForms.apiKeyRequired")),
    [FIELD_DEFAULT_MODEL_NAME]: Yup.string().required(t("llmOnboardingForms.modelNameRequired")),
  });

  const icon = () => (
    <ConnectionProviderIcon
      icon={<ProviderIcon provider={llmDescriptor.name} size={24} />}
    />
  );

  return (
    <OnboardingFormWrapper<OpenRouterFormValues>
      icon={icon}
      title={t("llmOnboarding.setupOpenRouter")}
      description={t("llmOnboarding.setupOpenRouterDesc")}
      llmDescriptor={llmDescriptor}
      onboardingState={onboardingState}
      onboardingActions={onboardingActions}
      open={open}
      onOpenChange={onOpenChange}
      initialValues={initialValues}
      validationSchema={validationSchema}
    >
      {(props) => <OpenRouterFormFields {...props} />}
    </OnboardingFormWrapper>
  );
}
