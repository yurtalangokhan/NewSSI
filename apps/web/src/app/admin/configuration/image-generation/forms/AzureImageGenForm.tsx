"use client";

import React, { useMemo } from "react";
import { useTranslation, Trans } from "react-i18next";
import * as Yup from "yup";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputComboBox from "@/refresh-components/inputs/InputComboBox";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import { ImageGenFormWrapper } from "./ImageGenFormWrapper";
import {
  ImageGenFormBaseProps,
  ImageGenFormChildProps,
  ImageGenSubmitPayload,
} from "./types";
import { ImageGenerationCredentials } from "@/lib/configuration/imageConfigurationService";
import { ImageProvider } from "../constants";
import {
  parseAzureTargetUri,
  isValidAzureTargetUri,
} from "@/lib/azureTargetUri";

// Azure form values - target URI and API key
interface AzureFormValues {
  target_uri: string;
  api_key: string;
}

const initialValues: AzureFormValues = {
  target_uri: "",
  api_key: "",
};

function AzureFormFields(props: ImageGenFormChildProps<AzureFormValues>) {
  const {
    formikProps,
    apiStatus,
    showApiMessage,
    errorMessage,
    disabled,
    isLoadingCredentials,
    apiKeyOptions,
    resetApiState,
    imageProvider,
  } = props;
  const { t } = useTranslation();

  return (
    <>
      {/* Target URI field */}
      <FormikField<string>
        name="target_uri"
        render={(field, helper, meta, state) => (
          <FormField name="target_uri" state={state} className="w-full">
            <FormField.Label>
              {t("admin.imageGeneration.forms.azure.targetUriLabel")}
            </FormField.Label>
            <FormField.Control>
              <InputTypeIn
                {...field}
                placeholder="https://your-resource.cognitiveservices.azure.com/openai/deployments/deployment-name/images/generations?api-version=2025-01-01-preview"
                showClearButton={false}
                variant={disabled ? "disabled" : undefined}
              />
            </FormField.Control>
            <FormField.Message
              messages={{
                idle: (
                  <Trans
                    i18nKey="admin.imageGeneration.forms.azure.targetUriHint"
                    values={{ link: "Azure OpenAI" }}
                    components={{
                      link: (
                        <a
                          href="https://oai.azure.com"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        />
                      ),
                    }}
                  />
                ),
                error: meta.error,
              }}
            />
          </FormField>
        )}
      />

      {/* API Key field */}
      <FormikField<string>
        name="api_key"
        render={(field, helper, meta, state) => (
          <FormField
            name="api_key"
            state={apiStatus === "error" ? "error" : state}
            className="w-full"
          >
            <FormField.Label>
              {t("admin.imageGeneration.forms.apiKeyLabel")}
            </FormField.Label>
            <FormField.Control>
              {apiKeyOptions.length > 0 ? (
                <InputComboBox
                  value={field.value}
                  onChange={(e) => {
                    helper.setValue(e.target.value);
                    resetApiState();
                  }}
                  onValueChange={(value) => {
                    helper.setValue(value);
                    resetApiState();
                  }}
                  onBlur={field.onBlur}
                  options={apiKeyOptions}
                  placeholder={
                    isLoadingCredentials
                      ? t(
                          "admin.imageGeneration.forms.apiKeyPlaceholderLoading"
                        )
                      : t("admin.imageGeneration.forms.apiKeyPlaceholderSelect")
                  }
                  disabled={disabled || !formikProps.values.target_uri?.trim()}
                  isError={apiStatus === "error"}
                />
              ) : (
                <PasswordInputTypeIn
                  {...field}
                  onChange={(e) => {
                    field.onChange(e);
                    resetApiState();
                  }}
                  placeholder={
                    isLoadingCredentials
                      ? t(
                          "admin.imageGeneration.forms.apiKeyPlaceholderLoading"
                        )
                      : t("admin.imageGeneration.forms.apiKeyPlaceholder")
                  }
                  showClearButton={false}
                  disabled={disabled || !formikProps.values.target_uri?.trim()}
                  error={apiStatus === "error"}
                />
              )}
            </FormField.Control>
            {showApiMessage ? (
              <FormField.APIMessage
                state={apiStatus}
                messages={{
                  loading: t("admin.imageGeneration.forms.testingApiKey", {
                    name: imageProvider.title,
                  }),
                  success: t("admin.imageGeneration.forms.apiKeyValid"),
                  error:
                    errorMessage ||
                    t("admin.imageGeneration.forms.apiKeyInvalid"),
                }}
              />
            ) : (
              <FormField.Message
                messages={{
                  idle: (
                    <Trans
                      i18nKey="admin.imageGeneration.forms.azure.apiKeyHint"
                      values={{ link: "API key" }}
                      components={{
                        link: (
                          <a
                            href="https://oai.azure.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline"
                          />
                        ),
                      }}
                    />
                  ),
                  error: meta.error,
                }}
              />
            )}
          </FormField>
        )}
      />
    </>
  );
}

function getInitialValuesFromCredentials(
  credentials: ImageGenerationCredentials,
  imageProvider: ImageProvider
): Partial<AzureFormValues> {
  // Reconstruct target_uri from credentials
  let targetUri = "";
  if (credentials.api_base && credentials.api_version) {
    const deployment = credentials.deployment_name || imageProvider.model_name;
    targetUri = `${credentials.api_base}/openai/deployments/${deployment}/images/generations?api-version=${credentials.api_version}`;
  }

  return {
    api_key: credentials.api_key || "",
    target_uri: targetUri,
  };
}

function transformValues(
  values: AzureFormValues,
  imageProvider: ImageProvider
): ImageGenSubmitPayload {
  // Parse target_uri to extract api_base, api_version, deployment_name
  let apiBase: string | undefined;
  let apiVersion: string | undefined;
  let deploymentName: string | undefined;
  let modelName = imageProvider.model_name;

  if (values.target_uri) {
    try {
      const parsed = parseAzureTargetUri(values.target_uri);
      apiBase = parsed.url.origin;
      apiVersion = parsed.apiVersion;
      deploymentName = parsed.deploymentName || undefined;
      // For Azure, use deployment name as model name
      modelName = deploymentName || imageProvider.model_name;
    } catch (error) {
      console.error("Failed to parse target_uri:", error);
    }
  }

  return {
    modelName,
    imageProviderId: imageProvider.image_provider_id,
    provider: "azure",
    apiKey: values.api_key,
    apiBase,
    apiVersion,
    deploymentName,
  };
}

export function AzureImageGenForm(props: ImageGenFormBaseProps) {
  const { imageProvider, existingConfig } = props;
  const { t } = useTranslation();

  const validationSchema = useMemo(
    () =>
      Yup.object().shape({
        target_uri: Yup.string()
          .required(t("admin.imageGeneration.forms.azure.targetUriRequired"))
          .test(
            "valid-target-uri",
            t("admin.imageGeneration.forms.azure.targetUriInvalid"),
            (value) => (value ? isValidAzureTargetUri(value) : false)
          ),
        api_key: Yup.string().required(
          t("admin.imageGeneration.forms.apiKeyRequired")
        ),
      }),
    [t]
  );

  return (
    <ImageGenFormWrapper<AzureFormValues>
      {...props}
      title={
        existingConfig
          ? t("admin.imageGeneration.forms.editTitle", {
              name: imageProvider.title,
            })
          : t("admin.imageGeneration.forms.connectTitle", {
              name: imageProvider.title,
            })
      }
      description={
        imageProvider.descriptionKey
          ? t(imageProvider.descriptionKey)
          : imageProvider.description
      }
      initialValues={initialValues}
      validationSchema={validationSchema}
      getInitialValuesFromCredentials={getInitialValuesFromCredentials}
      transformValues={(values) => transformValues(values, imageProvider)}
    >
      {(childProps) => <AzureFormFields {...childProps} />}
    </ImageGenFormWrapper>
  );
}
