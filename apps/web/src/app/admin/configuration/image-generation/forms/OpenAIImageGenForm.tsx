"use client";

import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import * as Yup from "yup";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
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

// OpenAI form values - just API key
interface OpenAIFormValues {
  api_key: string;
}

const initialValues: OpenAIFormValues = {
  api_key: "",
};

function OpenAIFormFields(props: ImageGenFormChildProps<OpenAIFormValues>) {
  const {
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
    <FormikField<string>
      name="api_key"
      render={(field, helper, meta, state) => (
        <FormField
          name="api_key"
          state={apiStatus === "error" ? "error" : state}
          className="w-full"
        >
          <FormField.Label>{t("admin.imageGeneration.forms.apiKeyLabel")}</FormField.Label>
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
                    ? t("admin.imageGeneration.forms.apiKeyPlaceholderLoading")
                    : t("admin.imageGeneration.forms.apiKeyPlaceholderSelect")
                }
                disabled={disabled}
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
                    ? t("admin.imageGeneration.forms.apiKeyPlaceholderLoading")
                    : t("admin.imageGeneration.forms.apiKeyPlaceholder")
                }
                showClearButton={false}
                disabled={disabled}
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
                error: errorMessage || t("admin.imageGeneration.forms.apiKeyInvalid"),
              }}
            />
          ) : (
            <FormField.Message
              messages={{
                idle: t("admin.imageGeneration.forms.apiKeyHint"),
                error: meta.error,
              }}
            />
          )}
        </FormField>
      )}
    />
  );
}

function getInitialValuesFromCredentials(
  credentials: ImageGenerationCredentials,
  _imageProvider: ImageProvider
): Partial<OpenAIFormValues> {
  return {
    api_key: credentials.api_key || "",
  };
}

function transformValues(
  values: OpenAIFormValues,
  imageProvider: ImageProvider
): ImageGenSubmitPayload {
  return {
    modelName: imageProvider.model_name,
    imageProviderId: imageProvider.image_provider_id,
    provider: "openai",
    apiKey: values.api_key,
  };
}

export function OpenAIImageGenForm(props: ImageGenFormBaseProps) {
  const { imageProvider, existingConfig } = props;
  const { t } = useTranslation();

  const validationSchema = useMemo(
    () =>
      Yup.object().shape({
        api_key: Yup.string().required(t("admin.imageGeneration.forms.apiKeyRequired")),
      }),
    [t]
  );

  return (
    <ImageGenFormWrapper<OpenAIFormValues>
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
      {(childProps) => <OpenAIFormFields {...childProps} />}
    </ImageGenFormWrapper>
  );
}
