"use client";

import { useTranslation } from "react-i18next";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import { ModelSelector } from "../../../../components/embedding/ModelSelector";
import {
  AVAILABLE_MODELS,
  CloudEmbeddingModel,
  HostedEmbeddingModel,
} from "../../../../components/embedding/interfaces";
import { CustomModelForm } from "../../../../components/embedding/CustomModelForm";
import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
export default function OpenEmbeddingPage({
  onSelectOpenSource,
  selectedProvider,
}: {
  onSelectOpenSource: (model: HostedEmbeddingModel) => void;
  selectedProvider: HostedEmbeddingModel | CloudEmbeddingModel;
}) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.embeddings.openPage",
  });
  const [configureModel, setConfigureModel] = useState(false);
  return (
    <div>
      <Title className="mt-8">{t("localModelsTitle")}</Title>
      <Text className="mb-4">{t("localModelsDescription")}</Text>
      <ModelSelector
        modelOptions={AVAILABLE_MODELS}
        setSelectedModel={onSelectOpenSource}
        currentEmbeddingModel={selectedProvider}
      />

      <Text className="mt-6">
        {t("alternativelyPrefix")}{" "}
        <a
          target="_blank"
          href="https://www.sbert.net/"
          className="text-link"
          rel="noreferrer"
        >
          {t("sentenceTransformersLink")}
        </a>
        {t("alternativelyMiddle")}{" "}
        <a
          target="_blank"
          href="https://huggingface.co/models?library=sentence-transformers&sort=trending"
          className="text-link"
          rel="noreferrer"
        >
          {t("hereLink")}
        </a>
        .
        <br />
        <b>{t("noteLabel")}</b> {t("modelListNote")}
      </Text>
      {!configureModel && (
        <Button
          onClick={() => setConfigureModel(true)}
          className="mt-4"
          secondary
        >
          {t("configureCustomModelButton")}
        </Button>
      )}
      {configureModel && (
        <div className="w-full flex">
          <CardSection className="mt-4 2xl:w-4/6 mx-auto">
            <CustomModelForm onSubmit={onSelectOpenSource} />
          </CardSection>
        </div>
      )}
    </div>
  );
}
