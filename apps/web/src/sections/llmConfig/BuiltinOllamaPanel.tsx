"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSWRConfig } from "swr";
import { Button } from "@opal/components";
import { ContentAction } from "@opal/layouts";
import {
  SvgAlertCircle,
  SvgCheckCircle,
  SvgDownload,
  SvgRefreshCw,
  SvgTrash,
} from "@opal/icons";
import Card from "@/refresh-components/cards/Card";
import Text from "@/refresh-components/texts/Text";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import { Section } from "@/layouts/general-layouts";
import { toast } from "@/hooks/useToast";
import {
  useBuiltinOllamaModels,
  useBuiltinOllamaStatus,
  useDeleteBuiltinOllamaModel,
} from "@/hooks/useProviders";
import { BuiltinOllamaStatus, OllamaModelResponse } from "@/interfaces/llm";
import { getProviderIcon } from "@/lib/llmConfig/providers";

interface ViewProps {
  status?: BuiltinOllamaStatus;
  models: OllamaModelResponse[];
  isLoading: boolean;
  isDeleting: boolean;
  onRefresh: () => void;
  onDownload: () => void;
  onDeleteModel: (modelName: string) => void;
}

function formatModelSize(size?: number) {
  if (!size || size < 50_000_000) {
    return null;
  }
  return `${(size / 1_000_000_000).toFixed(1)} GB`;
}

export function BuiltinOllamaPanelView({
  status,
  models,
  isLoading,
  isDeleting,
  onRefresh,
  onDownload,
  onDeleteModel,
}: ViewProps) {
  const { t } = useTranslation("common", { keyPrefix: "admin.builtinOllama" });
  const ProviderIcon = getProviderIcon("ollama");
  const online = status?.online === true;
  const statusLabel = online ? t("online") : t("offline");

  return (
    <Card padding={0.75} className="w-full">
      <ContentAction
        icon={ProviderIcon}
        title={t("title")}
        description={status?.base_url ?? t("configuredByRuntime")}
        sizePreset="main-content"
        variant="section"
        tag={{
          title: statusLabel,
          color: online ? "green" : "amber",
        }}
        rightChildren={
          <Section flexDirection="row" gap={0} alignItems="center">
            <Button
              icon={SvgRefreshCw}
              prominence="tertiary"
              aria-label={t("refreshAriaLabel")}
              onClick={onRefresh}
            />
            <Button
              icon={SvgDownload}
              prominence="tertiary"
              aria-label={t("downloadAriaLabel")}
              onClick={onDownload}
            />
          </Section>
        }
      />

      <div className="w-full mt-3 flex flex-col gap-3 border-t border-border pt-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {online ? (
            <SvgCheckCircle className="h-4 w-4 text-success" />
          ) : (
            <SvgAlertCircle className="h-4 w-4 text-warning" />
          )}
          <Text text03>{statusLabel}</Text>
          {status?.version && (
            <Text text03>{t("versionLabel", { version: status.version })}</Text>
          )}
          <Text text03>
            {t("modelsCount", {
              count: models.length || status?.model_count || 0,
            })}
          </Text>
        </div>

        {status?.error && (
          <Text text03 className="text-warning">
            {status.error}
          </Text>
        )}

        {isLoading ? (
          <div className="flex items-center gap-2 py-2">
            <SvgRefreshCw className="h-4 w-4 animate-spin text-text-03" />
            <Text text03>{t("loadingModels")}</Text>
          </div>
        ) : models.length > 0 ? (
          <div className="flex w-full flex-col gap-1">
            {models.map((model) => {
              const modelSize = formatModelSize(model.size);
              return (
                <div
                  key={model.name}
                  className="flex w-full min-h-9 items-center gap-2 rounded-md px-2 py-1.5 hover:bg-background-neutral-03 transition-colors"
                >
                  <span className="font-mono text-sm text-text-04 truncate mr-1">
                    {model.display_name || model.name}
                  </span>
                  <div className="flex items-center gap-1">
                    {model.supports_image_input && (
                      <span
                        title={t("supportsImageInput")}
                        className="rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("visionTag")}
                      </span>
                    )}
                    {model.supports_reasoning && (
                      <span
                        title={t("supportsReasoning")}
                        className="rounded bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("reasoningTag")}
                      </span>
                    )}
                    {model.supports_tools && (
                      <span
                        title={t("supportsTools")}
                        className="rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("toolsTag")}
                      </span>
                    )}
                    {model.supports_embedding && (
                      <span
                        title={t("supportsEmbedding")}
                        className="rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("embeddingTag")}
                      </span>
                    )}
                    {model.supports_code && (
                      <span
                        title={t("supportsCode")}
                        className="rounded bg-cyan-100 dark:bg-cyan-900/40 text-cyan-700 dark:text-cyan-300 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("codeTag")}
                      </span>
                    )}
                    {model.supports_audio && (
                      <span
                        title={t("supportsAudio")}
                        className="rounded bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("audioTag")}
                      </span>
                    )}
                    {model.is_remote && (
                      <span
                        title={t("cloudTag")}
                        className="rounded bg-background-neutral-03 text-text-03 px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        {t("cloudTag")}
                      </span>
                    )}
                  </div>
                  <span className="flex-1" />
                  {model.max_input_tokens != null && (
                    <span className="text-xs tabular-nums text-text-03 mr-2">
                      {model.max_input_tokens.toLocaleString()}{" "}
                      {t("contextSuffix")}
                    </span>
                  )}
                  {modelSize && (
                    <span className="w-16 text-right text-xs tabular-nums text-text-03 mr-1">
                      {modelSize}
                    </span>
                  )}
                  <Button
                    icon={SvgTrash}
                    prominence="tertiary"
                    aria-label={t("deleteModelAriaLabel", {
                      model: model.name,
                    })}
                    disabled={isDeleting}
                    onClick={() => onDeleteModel(model.name)}
                  />
                </div>
              );
            })}
          </div>
        ) : (
          <Text text03>{t("noModelsInstalled")}</Text>
        )}
      </div>
    </Card>
  );
}

interface Props {
  onDownload: () => void;
}

export function BuiltinOllamaPanel({ onDownload }: Props) {
  const { t } = useTranslation("common", { keyPrefix: "admin.builtinOllama" });
  const { t: tRoot } = useTranslation("common");
  const { mutate } = useSWRConfig();
  const status = useBuiltinOllamaStatus();
  const models = useBuiltinOllamaModels();
  const deleteModel = useDeleteBuiltinOllamaModel();
  const [deletingModel, setDeletingModel] = useState<string | null>(null);
  const [modelToDelete, setModelToDelete] = useState<string | null>(null);

  const refresh = () => {
    status.mutate();
    models.mutate();
  };

  const handleDeleteModel = async (modelName: string) => {
    setDeletingModel(modelName);
    try {
      await deleteModel(modelName);
      await Promise.all([
        status.mutate(),
        models.mutate(),
        mutate("/api/admin/providers"),
        mutate("/api/admin/providers/available-models"),
      ]);
      toast({ message: t("deletedToast", { model: modelName }) });
      setModelToDelete(null);
    } catch (error) {
      toast({
        message:
          error instanceof Error ? error.message : t("deleteFailedToast"),
        level: "error",
      });
    } finally {
      setDeletingModel(null);
    }
  };

  return (
    <>
      {modelToDelete && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("deleteModelConfirmTitle")}
          onClose={() => {
            if (deletingModel === null) {
              setModelToDelete(null);
            }
          }}
          submit={
            <Button
              variant="danger"
              disabled={deletingModel !== null}
              onClick={() => handleDeleteModel(modelToDelete)}
            >
              {deletingModel ? t("deletingModel") : tRoot("sidebar.delete")}
            </Button>
          }
        >
          <Text text03>
            {t("deleteModelConfirmBody", { model: modelToDelete })}
          </Text>
        </ConfirmationModalLayout>
      )}

      <BuiltinOllamaPanelView
        status={status.data}
        models={models.data}
        isLoading={status.isLoading || models.isLoading}
        isDeleting={deletingModel !== null}
        onRefresh={refresh}
        onDownload={onDownload}
        onDeleteModel={(modelName) => setModelToDelete(modelName)}
      />
    </>
  );
}
