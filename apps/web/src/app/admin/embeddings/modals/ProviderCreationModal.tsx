import React, { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import { Callout } from "@/components/ui/callout";
import Button from "@/refresh-components/buttons/Button";
import { Formik, Form } from "formik";
import * as Yup from "yup";
import { Label, TextFormField } from "@/components/Field";
import { LoadingAnimation } from "@/components/Loading";
import {
  CloudEmbeddingProvider,
  EmbeddingProvider,
  getFormattedProviderName,
} from "@/components/embedding/interfaces";
import { EMBEDDING_PROVIDERS_ADMIN_URL } from "@/lib/llmConfig/constants";
import Modal from "@/refresh-components/Modal";
import { SvgSettings } from "@opal/icons";
export interface ProviderCreationModalProps {
  updateCurrentModel: (
    newModel: string,
    provider_type: EmbeddingProvider
  ) => void;
  selectedProvider: CloudEmbeddingProvider;
  onConfirm: () => void;
  onCancel: () => void;
  existingProvider?: CloudEmbeddingProvider;
  isProxy?: boolean;
  isAzure?: boolean;
}

export default function ProviderCreationModal({
  selectedProvider,
  onConfirm,
  onCancel,
  existingProvider,
  isProxy,
  isAzure,
  updateCurrentModel,
}: ProviderCreationModalProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.embeddings.providerCreation",
  });
  const useFileUpload =
    selectedProvider.provider_type == EmbeddingProvider.GOOGLE;

  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");

  const initialValues = {
    provider_type:
      existingProvider?.provider_type || selectedProvider.provider_type,
    api_key: existingProvider?.api_key || "",
    api_url: existingProvider?.api_url || "",
    custom_config: existingProvider?.custom_config
      ? Object.entries(existingProvider.custom_config)
      : [],
    model_id: 0,
    model_name: null,
  };

  const validationSchema = Yup.object({
    provider_type: Yup.string().required(t("providerTypeRequired")),
    api_key:
      isProxy || isAzure
        ? Yup.string()
        : useFileUpload
          ? Yup.string()
          : Yup.string().required(t("apiKeyRequiredValidation")),
    model_name: isProxy
      ? Yup.string().required(t("modelNameRequiredValidation"))
      : Yup.string().nullable(),
    api_url:
      isProxy || isAzure
        ? Yup.string().required(t("apiUrlRequiredValidation"))
        : Yup.string(),
    deployment_name: isAzure
      ? Yup.string().required(t("deploymentNameRequiredValidation"))
      : Yup.string(),
    api_version: isAzure
      ? Yup.string().required(t("apiVersionRequiredValidation"))
      : Yup.string(),
    custom_config: Yup.array().of(Yup.array().of(Yup.string()).length(2)),
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
    setFieldValue: (field: string, value: any) => void
  ) => {
    const file = event.target.files?.[0];
    setFileName("");
    if (file) {
      setFileName(file.name);
      try {
        const fileContent = await file.text();
        let jsonContent;
        try {
          jsonContent = JSON.parse(fileContent);
        } catch (parseError) {
          throw new Error(t("jsonParseError"));
        }
        setFieldValue("api_key", JSON.stringify(jsonContent));
      } catch (error) {
        setFieldValue("api_key", "");
      }
    }
  };

  const handleSubmit = async (
    values: any,
    { setSubmitting }: { setSubmitting: (isSubmitting: boolean) => void }
  ) => {
    setIsProcessing(true);
    setErrorMsg("");
    try {
      const customConfig = Object.fromEntries(values.custom_config);
      const providerType = values.provider_type.toLowerCase().split(" ")[0];
      const isOpenAI = providerType === "openai";

      const testModelName =
        isOpenAI || isAzure ? "text-embedding-3-small" : values.model_name;

      const testEmbeddingPayload = {
        provider_type: providerType,
        api_key: values.api_key,
        api_url: values.api_url,
        model_name: testModelName,
        api_version: values.api_version,
        deployment_name: values.deployment_name,
      };

      const initialResponse = await fetch(
        "/api/admin/embedding/test-embedding",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(testEmbeddingPayload),
        }
      );

      if (!initialResponse.ok) {
        const errorMsg = (await initialResponse.json()).detail;
        setErrorMsg(errorMsg);
        setIsProcessing(false);
        setSubmitting(false);
        return;
      }

      const response = await fetch(EMBEDDING_PROVIDERS_ADMIN_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...values,
          api_version: values.api_version,
          deployment_name: values.deployment_name,
          provider_type: values.provider_type.toLowerCase().split(" ")[0],
          custom_config: customConfig,
          is_default_provider: false,
          is_configured: true,
        }),
      });

      if (isAzure) {
        updateCurrentModel(values.model_name, EmbeddingProvider.AZURE);
      }

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || t("updateFailedFallback"));
      }

      onConfirm();
    } catch (error: unknown) {
      if (error instanceof Error) {
        setErrorMsg(error.message);
      } else {
        setErrorMsg(t("unknownError"));
      }
    } finally {
      setIsProcessing(false);
      setSubmitting(false);
    }
  };

  return (
    <Modal open onOpenChange={onCancel}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgSettings}
          title={t("configureTitle", {
            provider: getFormattedProviderName(selectedProvider.provider_type),
          })}
          onClose={onCancel}
        />
        <Modal.Body>
          <Formik
            initialValues={initialValues}
            validationSchema={validationSchema}
            onSubmit={handleSubmit}
          >
            {({ isSubmitting, handleSubmit, setFieldValue }) => (
              <Form onSubmit={handleSubmit} className="space-y-4">
                <Text as="p">
                  {t("credentialsInstructionsPrefix")}{" "}
                  <a
                    className="cursor-pointer underline"
                    target="_blank"
                    href={selectedProvider.docsLink}
                    rel="noreferrer"
                  >
                    {t("credentialsInstructionsHereLink")}
                  </a>{" "}
                  {t("credentialsInstructionsMiddle")}{" "}
                  <a
                    className="cursor-pointer underline"
                    target="_blank"
                    href={selectedProvider.apiLink}
                    rel="noreferrer"
                  >
                    {isProxy || isAzure
                      ? t("apiUrlLinkText")
                      : t("apiKeyLinkText")}
                  </a>{" "}
                  {t("credentialsInstructionsSuffix")}
                </Text>

                <div className="flex w-full flex-col gap-y-6">
                  {(isProxy || isAzure) && (
                    <TextFormField
                      name="api_url"
                      label={t("apiUrlLabel")}
                      placeholder={t("apiUrlLabel")}
                      type="text"
                    />
                  )}

                  {isProxy && (
                    <TextFormField
                      name="model_name"
                      label={`${t("modelNameLabel")} ${
                        isProxy ? t("modelNameForTestingSuffix") : ""
                      }`}
                      placeholder={t("modelNameLabel")}
                      type="text"
                    />
                  )}

                  {isAzure && (
                    <TextFormField
                      name="deployment_name"
                      label={t("deploymentNameLabel")}
                      placeholder={t("deploymentNameLabel")}
                      type="text"
                    />
                  )}

                  {isAzure && (
                    <TextFormField
                      name="api_version"
                      label={t("apiVersionLabel")}
                      placeholder={t("apiVersionLabel")}
                      type="text"
                    />
                  )}

                  {useFileUpload ? (
                    <>
                      <Label>{t("uploadJsonFileLabel")}</Label>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".json"
                        onChange={(e) => handleFileUpload(e, setFieldValue)}
                        className="text-lg w-full p-1"
                      />
                      {fileName && <p>{t("uploadedFileText", { fileName })}</p>}
                    </>
                  ) : (
                    <TextFormField
                      name="api_key"
                      label={`${t("apiKeyLabel")} ${
                        isProxy ? t("apiKeyForNonLocalSuffix") : ""
                      }`}
                      placeholder={t("apiKeyLabel")}
                      type="password"
                    />
                  )}

                  <a
                    href={selectedProvider.apiLink}
                    target="_blank"
                    className="underline cursor-pointer"
                    rel="noreferrer"
                  >
                    {t("learnMoreLink")}
                  </a>
                </div>

                {errorMsg && (
                  <Callout title={t("errorTitle")} type="danger">
                    {errorMsg}
                  </Callout>
                )}

                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting}
                >
                  {isProcessing ? (
                    <LoadingAnimation />
                  ) : existingProvider ? (
                    t("updateButton")
                  ) : (
                    t("createButton")
                  )}
                </Button>
              </Form>
            )}
          </Formik>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
