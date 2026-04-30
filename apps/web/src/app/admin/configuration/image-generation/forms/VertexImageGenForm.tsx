"use client";

import React, { useMemo } from "react";
import * as Yup from "yup";
import { useTranslation, Trans } from "react-i18next";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputFile from "@/refresh-components/inputs/InputFile";
import InlineExternalLink from "@/refresh-components/InlineExternalLink";
import { ImageGenFormWrapper } from "./ImageGenFormWrapper";
import {
  ImageGenFormBaseProps,
  ImageGenFormChildProps,
  ImageGenSubmitPayload,
} from "./types";
import { ImageProvider } from "../constants";
import { ImageGenerationCredentials } from "@/lib/configuration/imageConfigurationService";

const VERTEXAI_PROVIDER_NAME = "vertex_ai";
const VERTEXAI_DEFAULT_LOCATION = "global";

// Vertex form values
interface VertexImageGenFormValues {
  custom_config: {
    vertex_credentials: string;
    vertex_location: string;
  };
}

const initialValues: VertexImageGenFormValues = {
  custom_config: {
    vertex_credentials: "",
    vertex_location: VERTEXAI_DEFAULT_LOCATION,
  },
};

function getInitialValuesFromCredentials(
  credentials: ImageGenerationCredentials,
  _imageProvider: ImageProvider
): Partial<VertexImageGenFormValues> {
  return {
    custom_config: {
      vertex_credentials: credentials.custom_config?.vertex_credentials || "",
      vertex_location:
        credentials.custom_config?.vertex_location || VERTEXAI_DEFAULT_LOCATION,
    },
  };
}

function transformValues(
  values: VertexImageGenFormValues,
  imageProvider: ImageProvider
): ImageGenSubmitPayload {
  return {
    modelName: imageProvider.model_name,
    imageProviderId: imageProvider.image_provider_id,
    provider: VERTEXAI_PROVIDER_NAME,
    customConfig: {
      vertex_credentials: values.custom_config.vertex_credentials,
      vertex_location: values.custom_config.vertex_location,
    },
  };
}

function VertexFormFields(
  props: ImageGenFormChildProps<VertexImageGenFormValues>
) {
  const { apiStatus, showApiMessage, errorMessage, disabled, imageProvider } =
    props;
  const { t } = useTranslation();

  return (
    <>
      {/* Credentials File field */}
      <FormikField<string>
        name="custom_config.vertex_credentials"
        render={(field, helper, meta, state) => (
          <FormField
            name="custom_config.vertex_credentials"
            state={apiStatus === "error" ? "error" : state}
            className="w-full"
          >
            <FormField.Label>
              {t("admin.imageGeneration.forms.vertex.credentialsFileLabel")}
            </FormField.Label>
            <FormField.Control>
              <InputFile
                setValue={(value) => helper.setValue(value)}
                error={apiStatus === "error"}
                onBlur={field.onBlur}
                showClearButton={true}
                disabled={disabled}
                accept="application/json"
                placeholder={t(
                  "admin.imageGeneration.forms.vertex.credentialsPlaceholder"
                )}
              />
            </FormField.Control>
            {showApiMessage ? (
              <FormField.APIMessage
                state={apiStatus}
                messages={{
                  loading: t("admin.imageGeneration.forms.vertex.testingCredentials", {
                    name: imageProvider.title,
                  }),
                  success: t("admin.imageGeneration.forms.vertex.credentialsValid"),
                  error:
                    errorMessage ||
                    t("admin.imageGeneration.forms.vertex.credentialsInvalid"),
                }}
              />
            ) : (
              <FormField.Message
                messages={{
                  idle: (
                    <Trans
                      i18nKey="admin.imageGeneration.forms.vertex.credentialsHint"
                      values={{ link: "service account credentials" }}
                      components={{
                        link: (
                          <InlineExternalLink href="https://console.cloud.google.com/projectselector2/iam-admin/serviceaccounts?supportedpurview=project">
                            service account credentials
                          </InlineExternalLink>
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

      {/* Location field */}
      <FormikField<string>
        name="custom_config.vertex_location"
        render={(field, helper, meta, state) => (
          <FormField
            name="custom_config.vertex_location"
            state={state}
            className="w-full"
          >
            <FormField.Label>
              {t("admin.imageGeneration.forms.vertex.locationLabel")}
            </FormField.Label>
            <FormField.Control>
              <InputTypeIn
                value={field.value}
                onChange={(e) => helper.setValue(e.target.value)}
                onBlur={field.onBlur}
                placeholder="global"
                showClearButton={false}
                variant={disabled ? "disabled" : undefined}
              />
            </FormField.Control>
            <FormField.Message
              messages={{
                idle: (
                  <Trans
                    i18nKey="admin.imageGeneration.forms.vertex.locationHint"
                    values={{ link: "Google's documentation" }}
                    components={{
                      link: (
                        <InlineExternalLink href="https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations">
                          Google&apos;s documentation
                        </InlineExternalLink>
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
    </>
  );
}

export function VertexImageGenForm(props: ImageGenFormBaseProps) {
  const { imageProvider, existingConfig } = props;
  const { t } = useTranslation();

  const validationSchema = useMemo(
    () =>
      Yup.object().shape({
        custom_config: Yup.object().shape({
          vertex_credentials: Yup.string().required(
            t("admin.imageGeneration.forms.vertex.credentialsFileRequired")
          ),
          vertex_location: Yup.string().required(
            t("admin.imageGeneration.forms.vertex.locationRequired")
          ),
        }),
      }),
    [t]
  );

  return (
    <ImageGenFormWrapper<VertexImageGenFormValues>
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
      {(childProps) => <VertexFormFields {...childProps} />}
    </ImageGenFormWrapper>
  );
}
