"use client";

import React, { useRef, useState } from "react";
import Modal from "@/refresh-components/Modal";
import { Callout } from "@/components/ui/callout";
import Text from "@/refresh-components/texts/Text";
import Separator from "@/refresh-components/Separator";
import Button from "@/refresh-components/buttons/Button";
import { Label } from "@/components/Field";
import {
  CloudEmbeddingProvider,
  getFormattedProviderName,
} from "@/components/embedding/interfaces";
import {
  EMBEDDING_PROVIDERS_ADMIN_URL,
  LLM_PROVIDERS_ADMIN_URL,
} from "@/lib/llmConfig/constants";
import { mutate } from "swr";
import { testEmbedding } from "@/app/admin/embeddings/pages/utils";
import { SvgSettings } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface ChangeCredentialsModalProps {
  provider: CloudEmbeddingProvider;
  onConfirm: () => void;
  onCancel: () => void;
  onDeleted: () => void;
  useFileUpload: boolean;
  isProxy?: boolean;
  isAzure?: boolean;
}

export default function ChangeCredentialsModal({
  provider,
  onConfirm,
  onCancel,
  onDeleted,
  useFileUpload,
  isProxy = false,
  isAzure = false,
}: ChangeCredentialsModalProps) {
  const { t } = useTranslation();
  const [apiKey, setApiKey] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [testError, setTestError] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deletionError, setDeletionError] = useState<string>("");

  const clearFileInput = () => {
    setFileName("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    setFileName("");

    if (file) {
      setFileName(file.name);
      try {
        setDeletionError("");
        const fileContent = await file.text();
        let jsonContent;
        try {
          jsonContent = JSON.parse(fileContent);
          setApiKey(JSON.stringify(jsonContent));
        } catch (parseError) {
          throw new Error(t("changeCredentials.failedParseJson"));
        }
      } catch (error) {
        setTestError(
          error instanceof Error
            ? error.message
            : t("changeCredentials.unknownFileError")
        );
        setApiKey("");
        clearFileInput();
      }
    }
  };

  const handleDelete = async () => {
    setDeletionError("");

    try {
      const response = await fetch(
        `${EMBEDDING_PROVIDERS_ADMIN_URL}/${provider.provider_type.toLowerCase()}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        setDeletionError(errorData.detail);
        return;
      }

      mutate(LLM_PROVIDERS_ADMIN_URL);
      onDeleted();
    } catch (error) {
      setDeletionError(
        error instanceof Error
          ? error.message
          : t("changeCredentials.unknownError")
      );
    }
  };

  const handleSubmit = async () => {
    setTestError("");
    const normalizedProviderType = provider.provider_type
      .toLowerCase()
      .split(" ")[0];

    if (!normalizedProviderType) {
      setTestError(t("changeCredentials.providerTypeInvalid"));
      return;
    }

    try {
      const testResponse = await testEmbedding({
        provider_type: normalizedProviderType,
        modelName,
        apiKey,
        apiUrl,
        apiVersion: null,
        deploymentName: null,
      });

      if (!testResponse.ok) {
        const errorMsg = (await testResponse.json()).detail;
        throw new Error(errorMsg);
      }

      const updateResponse = await fetch(EMBEDDING_PROVIDERS_ADMIN_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: normalizedProviderType,
          api_key: apiKey,
          api_url: apiUrl,
          is_default_provider: false,
          is_configured: true,
        }),
      });

      if (!updateResponse.ok) {
        const errorData = await updateResponse.json();
        throw new Error(
          errorData.detail ||
            t("changeCredentials.failedUpdate", {
              type: isProxy ? "API URL" : "API key",
            })
        );
      }

      // Refresh cached provider details so the rest of the form sees the new key without forcing a re-index
      await mutate(EMBEDDING_PROVIDERS_ADMIN_URL);

      onConfirm();
    } catch (error) {
      setTestError(
        error instanceof Error
          ? error.message
          : t("changeCredentials.unknownError")
      );
    }
  };
  return (
    <Modal open onOpenChange={onCancel}>
      <Modal.Content>
        <Modal.Header
          icon={SvgSettings}
          title={
            isProxy
              ? t("changeCredentials.modifyConfigTitle", {
                  provider: getFormattedProviderName(provider.provider_type),
                })
              : t("changeCredentials.modifyKeyTitle", {
                  provider: getFormattedProviderName(provider.provider_type),
                })
          }
          onClose={onCancel}
        />
        <Modal.Body>
          {!isAzure && (
            <>
              <Text as="p">
                {isProxy
                  ? t("changeCredentials.modifyDescWithUrl")
                  : t("changeCredentials.modifyDesc")}
              </Text>

              <div className="flex flex-col gap-2">
                <Label className="mt-2">{t("changeCredentials.apiKey")}</Label>
                {useFileUpload ? (
                  <>
                    <Label className="mt-2">
                      {t("changeCredentials.uploadJson")}
                    </Label>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".json"
                      onChange={handleFileUpload}
                      className="text-lg w-full p-1"
                    />
                    {fileName && (
                      <p>
                        {t("changeCredentials.uploadedFile", {
                          name: fileName,
                        })}
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <input
                      type="password"
                      className="border border-border rounded w-full py-2 px-3 bg-background-emphasis"
                      value={apiKey}
                      onChange={(e: any) => setApiKey(e.target.value)}
                      placeholder={t("changeCredentials.pasteApiKey")}
                    />
                  </>
                )}

                {isProxy && (
                  <>
                    <Label className="mt-2">
                      {t("changeCredentials.apiUrl")}
                    </Label>

                    <input
                      className={`
                          border
                          border-border
                          rounded
                          w-full
                          py-2
                          px-3
                          bg-background-emphasis
                      `}
                      value={apiUrl}
                      onChange={(e: any) => setApiUrl(e.target.value)}
                      placeholder={t("changeCredentials.pasteApiUrl")}
                    />

                    {deletionError && (
                      <Callout type="danger" title={t("common.error")}>
                        {deletionError}
                      </Callout>
                    )}

                    <div>
                      <Label className="mt-2">
                        {t("changeCredentials.testModel")}
                      </Label>
                      <Text as="p">{t("changeCredentials.liteLlmNote")}</Text>
                    </div>
                    <input
                      className={`
                       border
                       border-border
                       rounded
                       w-full
                       py-2
                       px-3
                       bg-background-emphasis
                   `}
                      value={modelName}
                      onChange={(e: any) => setModelName(e.target.value)}
                      placeholder={t("changeCredentials.pasteModelName")}
                    />
                  </>
                )}

                {testError && (
                  <Callout type="danger" title={t("common.error")}>
                    {testError}
                  </Callout>
                )}

                <Button
                  className="mr-auto mt-4"
                  onClick={() => handleSubmit()}
                  disabled={!apiKey}
                >
                  {t("changeCredentials.updateConfig")}
                </Button>

                <Separator />
              </div>
            </>
          )}

          <Text as="p" className="mt-4 font-bold">
            {t("changeCredentials.canDelete")}
          </Text>
          <Text as="p">{t("changeCredentials.deleteNote")}</Text>

          <Button className="mr-auto" onClick={handleDelete} danger>
            {t("changeCredentials.deleteConfig")}
          </Button>
          {deletionError && (
            <Callout type="danger" title={t("common.error")}>
              {deletionError}
            </Callout>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
