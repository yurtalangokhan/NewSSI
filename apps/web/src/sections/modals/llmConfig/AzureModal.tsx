import { Form, Formik } from "formik";
import { TextFormField } from "@/components/Field";
import { LLMProviderFormProps, LLMProviderView } from "@/interfaces/llm";
import * as Yup from "yup";
import {
  ProviderFormEntrypointWrapper,
  ProviderFormContext,
} from "./components/FormWrapper";
import { DisplayNameField } from "./components/DisplayNameField";
import PasswordInputTypeInField from "@/refresh-components/form/PasswordInputTypeInField";
import { FormActionButtons } from "./components/FormActionButtons";
import {
  buildDefaultInitialValues,
  buildDefaultValidationSchema,
  buildAvailableModelConfigurations,
  submitLLMProvider,
  BaseLLMFormValues,
  LLM_FORM_CLASS_NAME,
} from "./formUtils";
import { AdvancedOptions } from "./components/AdvancedOptions";
import { SingleDefaultModelField } from "./components/SingleDefaultModelField";
import {
  isValidAzureTargetUri,
  parseAzureTargetUri,
} from "@/lib/azureTargetUri";
import Separator from "@/refresh-components/Separator";
import { useTranslation } from "react-i18next";

export const AZURE_PROVIDER_NAME = "azure";
const AZURE_DISPLAY_NAME = "Microsoft Azure Cloud";

interface AzureModalValues extends BaseLLMFormValues {
  api_key: string;
  target_uri: string;
  api_base?: string;
  api_version?: string;
}

const buildTargetUri = (existingLlmProvider?: LLMProviderView): string => {
  if (!existingLlmProvider?.api_base || !existingLlmProvider?.api_version) {
    return "";
  }
  return `${existingLlmProvider.api_base}/openai/deployments/your-deployment/chat/completions?api-version=${existingLlmProvider.api_version}`;
};

export function AzureModal({
  existingLlmProvider,
  shouldMarkAsDefault,
  open,
  onOpenChange,
}: LLMProviderFormProps) {
  return (
    <ProviderFormEntrypointWrapper
      providerName={AZURE_DISPLAY_NAME}
      providerEndpoint={AZURE_PROVIDER_NAME}
      existingLlmProvider={existingLlmProvider}
      open={open}
      onOpenChange={onOpenChange}
    >
      {({
        onClose,
        mutate,
        isTesting,
        setIsTesting,
        testError,
        setTestError,
        wellKnownLLMProvider,
      }: ProviderFormContext) => {
        const { t } = useTranslation();
        const modelConfigurations = buildAvailableModelConfigurations(
          existingLlmProvider,
          wellKnownLLMProvider
        );
        const initialValues: AzureModalValues = {
          ...buildDefaultInitialValues(
            existingLlmProvider,
            modelConfigurations
          ),
          api_key: existingLlmProvider?.api_key ?? "",
          target_uri: buildTargetUri(existingLlmProvider),
        };

        const validationSchema = buildDefaultValidationSchema().shape({
          api_key: Yup.string().required(t("llmConfig.apiKeyRequired")),
          target_uri: Yup.string()
            .required(t("llmConfig.targetUriRequired"))
            .test(
              "valid-target-uri",
              t("llmConfig.targetUriInvalid"),
              (value) => (value ? isValidAzureTargetUri(value) : false)
            ),
        });

        return (
          <Formik
            initialValues={initialValues}
            validationSchema={validationSchema}
            validateOnMount={true}
            onSubmit={async (values, { setSubmitting }) => {
              // Parse target_uri to extract api_base, api_version, and deployment_name
              let processedValues: AzureModalValues = { ...values };

              if (values.target_uri) {
                try {
                  const { url, apiVersion, deploymentName } =
                    parseAzureTargetUri(values.target_uri);
                  processedValues = {
                    ...processedValues,
                    api_base: url.origin,
                    api_version: apiVersion,
                  };
                } catch (error) {
                  console.error("Failed to parse target_uri:", error);
                }
              }

              await submitLLMProvider({
                providerName: AZURE_PROVIDER_NAME,
                values: processedValues,
                initialValues,
                modelConfigurations,
                existingLlmProvider,
                shouldMarkAsDefault,
                setIsTesting,
                setTestError,
                mutate,
                onClose,
                setSubmitting,
              });
            }}
          >
            {(formikProps) => {
              return (
                <Form className={LLM_FORM_CLASS_NAME}>
                  <DisplayNameField disabled={!!existingLlmProvider} />

                  <PasswordInputTypeInField name="api_key" label="API Key" />

                  <TextFormField
                    name="target_uri"
                    label={t("llmConfig.targetUriLabel")}
                    placeholder="https://your-resource.cognitiveservices.azure.com/openai/deployments/deployment-name/chat/completions?api-version=2025-01-01-preview"
                    subtext="The complete target URI for your deployment from the Azure AI portal."
                  />

                  <Separator />
                  <SingleDefaultModelField placeholder="E.g. gpt-4o" />
                  <Separator />

                  <AdvancedOptions formikProps={formikProps} />

                  <FormActionButtons
                    isTesting={isTesting}
                    testError={testError}
                    existingLlmProvider={existingLlmProvider}
                    mutate={mutate}
                    onClose={onClose}
                    isFormValid={formikProps.isValid}
                  />
                </Form>
              );
            }}
          </Formik>
        );
      }}
    </ProviderFormEntrypointWrapper>
  );
}
