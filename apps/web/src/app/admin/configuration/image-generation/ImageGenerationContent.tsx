"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import Text from "@/refresh-components/texts/Text";
import { Select } from "@/refresh-components/cards";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import { toast } from "@/hooks/useToast";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { LLMProviderResponse, LLMProviderView } from "@/interfaces/llm";
import { useTranslation } from "react-i18next";
import {
  IMAGE_PROVIDER_GROUPS,
  ImageProvider,
} from "@/app/admin/configuration/image-generation/constants";
import ImageGenerationConnectionModal from "@/app/admin/configuration/image-generation/ImageGenerationConnectionModal";
import {
  ImageGenerationConfigView,
  setDefaultImageGenerationConfig,
  unsetDefaultImageGenerationConfig,
} from "@/lib/configuration/imageConfigurationService";
import { ProviderIcon } from "@/app/admin/configuration/llm/ProviderIcon";
import Message from "@/refresh-components/messages/Message";

export default function ImageGenerationContent() {
  const {
    data: llmProviderResponse,
    error: llmError,
    mutate: refetchProviders,
  } = useSWR<LLMProviderResponse<LLMProviderView>>(
    "/api/admin/llm/provider?include_image_gen=true",
    errorHandlingFetcher
  );
  const { t } = useTranslation();
  const llmProviders = llmProviderResponse?.providers ?? [];

  const {
    data: configs = [],
    error: configError,
    mutate: refetchConfigs,
  } = useSWR<ImageGenerationConfigView[]>(
    "/api/admin/image-generation/config",
    errorHandlingFetcher
  );

  const modal = useCreateModal();
  const [activeProvider, setActiveProvider] = useState<ImageProvider | null>(
    null
  );
  const [editConfig, setEditConfig] =
    useState<ImageGenerationConfigView | null>(null);

  const connectedProviderIds = useMemo(() => {
    return new Set(configs.map((c) => c.image_provider_id));
  }, [configs]);

  const defaultConfig = useMemo(() => {
    return configs.find((c) => c.is_default);
  }, [configs]);

  const getStatus = (
    provider: ImageProvider
  ): "disconnected" | "connected" | "selected" => {
    if (defaultConfig?.image_provider_id === provider.image_provider_id)
      return "selected";
    if (connectedProviderIds.has(provider.image_provider_id))
      return "connected";
    return "disconnected";
  };

  const handleConnect = (provider: ImageProvider) => {
    setEditConfig(null);
    setActiveProvider(provider);
    modal.toggle(true);
  };

  const handleSelect = async (provider: ImageProvider) => {
    const config = configs.find(
      (c) => c.image_provider_id === provider.image_provider_id
    );
    if (config) {
      try {
        await setDefaultImageGenerationConfig(config.image_provider_id);
        toast.success(
          t("admin.imageGeneration.toastDefaultSet", { name: provider.title })
        );
        refetchConfigs();
      } catch (error) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("admin.imageGeneration.toastDefaultFailed")
        );
      }
    }
  };

  const handleDeselect = async (provider: ImageProvider) => {
    const config = configs.find(
      (c) => c.image_provider_id === provider.image_provider_id
    );
    if (config) {
      try {
        await unsetDefaultImageGenerationConfig(config.image_provider_id);
        toast.success(
          t("admin.imageGeneration.toastDeselected", { name: provider.title })
        );
        refetchConfigs();
      } catch (error) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("admin.imageGeneration.toastDeselectFailed")
        );
      }
    }
  };

  const handleEdit = (provider: ImageProvider) => {
    const config = configs.find(
      (c) => c.image_provider_id === provider.image_provider_id
    );
    setEditConfig(config || null);
    setActiveProvider(provider);
    modal.toggle(true);
  };

  const handleModalSuccess = () => {
    toast.success(t("admin.imageGeneration.toastConfigured"));
    setEditConfig(null);
    refetchConfigs();
    refetchProviders();
  };

  if (llmError || configError) {
    return (
      <div className="text-error">
        {t("admin.imageGeneration.errorLoadConfig")}
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-6">
        {/* Section Header */}
        <div className="flex flex-col gap-0.5">
          <Text mainContentEmphasis text05>
            {t("admin.imageGeneration.modelTitle")}
          </Text>
          <Text secondaryBody text03>
            {t("admin.imageGeneration.modelDescription")}
          </Text>
        </div>

        {connectedProviderIds.size === 0 && (
          <Message
            info
            static
            large
            close={false}
            text={t("admin.imageGeneration.connectModelMessage")}
            className="w-full"
          />
        )}

        {/* Provider Groups */}
        {IMAGE_PROVIDER_GROUPS.map((group) => (
          <div key={group.name} className="flex flex-col gap-2">
            <Text secondaryBody text03>
              {group.name}
            </Text>
            <div className="flex flex-col gap-2">
              {group.providers.map((provider) => (
                <Select
                  key={provider.image_provider_id}
                  aria-label={`image-gen-provider-${provider.image_provider_id}`}
                  icon={() => (
                    <ProviderIcon provider={provider.provider_name} size={18} />
                  )}
                  title={
                    provider.titleKey
                      ? t(provider.titleKey)
                      : provider.title
                  }
                  description={
                    provider.descriptionKey
                      ? t(provider.descriptionKey)
                      : provider.description
                  }
                  status={getStatus(provider)}
                  onConnect={() => handleConnect(provider)}
                  onSelect={() => handleSelect(provider)}
                  onDeselect={() => handleDeselect(provider)}
                  onEdit={() => handleEdit(provider)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {activeProvider && (
        <modal.Provider>
          <ImageGenerationConnectionModal
            modal={modal}
            imageProvider={activeProvider}
            existingProviders={llmProviders}
            existingConfig={editConfig || undefined}
            onSuccess={handleModalSuccess}
          />
        </modal.Provider>
      )}
    </>
  );
}
