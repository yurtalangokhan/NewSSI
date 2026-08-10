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
import { Section } from "@/layouts/general-layouts";
import { toast } from "@/hooks/useToast";
import {
  useBuiltinOllamaModels,
  useBuiltinOllamaStatus,
  useDeleteBuiltinOllamaModel,
} from "@/hooks/useProviders";
import {
  BuiltinOllamaStatus,
  OllamaModelResponse,
} from "@/interfaces/llm";
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
    <Card padding={0.75}>
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

      <div className="mt-3 flex flex-col gap-3 border-t border-border pt-3">
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
          <div className="flex flex-col gap-1">
            {models.map((model) => {
              const modelSize = formatModelSize(model.size);
              return (
                <div
                  key={model.name}
                  className="flex min-h-9 items-center gap-2 rounded-md px-2 py-1.5 hover:bg-background-neutral-03"
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-sm text-text-04">
                    {model.display_name || model.name}
                  </span>
                  {model.supports_reasoning && (
                    <span className="rounded bg-background-neutral-03 px-1.5 py-0.5 text-xs text-text-03">
                      {t("reasoningTag")}
                    </span>
                  )}
                  {model.max_input_tokens != null && (
                    <span className="text-xs tabular-nums text-text-03">
                      {model.max_input_tokens.toLocaleString()} {t("contextSuffix")}
                    </span>
                  )}
                  {modelSize && (
                    <span className="w-14 text-right text-xs tabular-nums text-text-03">
                      {modelSize}
                    </span>
                  )}
                  <Button
                    icon={SvgTrash}
                    prominence="tertiary"
                    aria-label={t("deleteModelAriaLabel", { model: model.name })}
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
  const { mutate } = useSWRConfig();
  const status = useBuiltinOllamaStatus();
  const models = useBuiltinOllamaModels();
  const deleteModel = useDeleteBuiltinOllamaModel();
  const [deletingModel, setDeletingModel] = useState<string | null>(null);

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
    } catch (error) {
      toast({
        message: error instanceof Error ? error.message : t("deleteFailedToast"),
        level: "error",
      });
    } finally {
      setDeletingModel(null);
    }
  };

  return (
    <BuiltinOllamaPanelView
      status={status.data}
      models={models.data}
      isLoading={status.isLoading || models.isLoading}
      isDeleting={deletingModel !== null}
      onRefresh={refresh}
      onDownload={onDownload}
      onDeleteModel={handleDeleteModel}
    />
  );
}
