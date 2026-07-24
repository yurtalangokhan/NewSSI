"use client";

import { useState, useMemo } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import {
  useAdminLLMProviders,
  useWellKnownLLMProviders,
} from "@/hooks/useLLMProviders";
import { useAvailableModels } from "@/hooks/useAvailableModels";
import {
  useAllProviders,
  useUrlProviders,
  useApiKeyProviders,
  useWellKnownLangChainProviders,
} from "@/hooks/useProviders";
import { ThreeDotsLoader } from "@/components/Loading";
import { Content, ContentAction } from "@opal/layouts";
import { Button } from "@opal/components";
import { Hoverable } from "@opal/core";
import { SvgArrowExchange, SvgSettings, SvgTrash } from "@opal/icons";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import * as GeneralLayouts from "@/layouts/general-layouts";
import {
  getProviderDisplayName,
  getProviderIcon,
  getProviderProductName,
} from "@/lib/llmConfig/providers";
import { deleteLlmProvider } from "@/lib/llmConfig/svc";
import Text from "@/refresh-components/texts/Text";
import { Horizontal as HorizontalInput } from "@/layouts/input-layouts";
import Card from "@/refresh-components/cards/Card";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Message from "@/refresh-components/messages/Message";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import Separator from "@/refresh-components/Separator";
import {
  LLMProviderView,
  WellKnownLLMProviderDescriptor,
  UrlBasedProvider,
  ApiKeyProvider,
  WellKnownLangChainProvider,
} from "@/interfaces/llm";
import { LLM_PROVIDERS_ADMIN_URL } from "@/lib/llmConfig/constants";
import { getModalForExistingProvider } from "@/sections/modals/llmConfig/getModal";
import { OpenAIModal } from "@/sections/modals/llmConfig/OpenAIModal";
import { AnthropicModal } from "@/sections/modals/llmConfig/AnthropicModal";
import { OllamaModal } from "@/sections/modals/llmConfig/OllamaModal";
import { AzureModal } from "@/sections/modals/llmConfig/AzureModal";
import { BedrockModal } from "@/sections/modals/llmConfig/BedrockModal";
import { VertexAIModal } from "@/sections/modals/llmConfig/VertexAIModal";
import { OpenRouterModal } from "@/sections/modals/llmConfig/OpenRouterModal";
import { CustomModal } from "@/sections/modals/llmConfig/CustomModal";
import { UrlProviderModal } from "@/sections/modals/llmConfig/UrlProviderModal";
import { ApiKeyProviderModal } from "@/sections/modals/llmConfig/ApiKeyProviderModal";
import { ModelDownloadModal } from "@/sections/modals/llmConfig/ModelDownloadModal";
import { UrlProviderCard } from "@/sections/llmConfig/UrlProviderCard";
import { BuiltinOllamaPanel } from "@/sections/llmConfig/BuiltinOllamaPanel";
import { EditProviderModal } from "@/sections/modals/llmConfig/EditProviderModal";
import { Section } from "@/layouts/general-layouts";
import { useTranslation } from "react-i18next";
import { useUser } from "@/providers/UserProvider";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.LLM_MODELS]!;

// ============================================================================
// Provider form mapping (keyed by provider name from the API)
// ============================================================================

const PROVIDER_MODAL_MAP: Record<
  string,
  (
    shouldMarkAsDefault: boolean,
    open: boolean,
    onOpenChange: (open: boolean) => void
  ) => React.ReactNode
> = {
  openai: (d, open, onOpenChange) => (
    <OpenAIModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
  anthropic: (d, open, onOpenChange) => (
    <AnthropicModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
  ollama_chat: (d, open, onOpenChange) => (
    <OllamaModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
  azure: (d, open, onOpenChange) => (
    <AzureModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
  bedrock: (d, open, onOpenChange) => (
    <BedrockModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
  vertex_ai: (d, open, onOpenChange) => (
    <VertexAIModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
  openrouter: (d, open, onOpenChange) => (
    <OpenRouterModal
      shouldMarkAsDefault={d}
      open={open}
      onOpenChange={onOpenChange}
    />
  ),
};

// ============================================================================
// ExistingProviderCard — card for configured (existing) providers
// ============================================================================

interface ExistingProviderCardProps {
  provider: LLMProviderView;
  isDefault: boolean;
  isLastProvider: boolean;
}

function ExistingProviderCard({
  provider,
  isDefault,
  isLastProvider,
}: ExistingProviderCardProps) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const [isOpen, setIsOpen] = useState(false);
  const deleteModal = useCreateModal();

  const handleDelete = async () => {
    try {
      await deleteLlmProvider(provider.id);
      mutate(LLM_PROVIDERS_ADMIN_URL);
      deleteModal.toggle(false);
      toast.success(t("admin.llm.providerDeletedSuccess"));
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      toast.error(t("admin.llm.deleteProviderFailed", { message }));
    }
  };

  return (
    <>
      {deleteModal.isOpen && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("admin.llm.deleteProviderTitle", { name: provider.name })}
          onClose={() => deleteModal.toggle(false)}
          submit={
            <Button variant="danger" onClick={handleDelete}>
              {t("sidebar.delete")}
            </Button>
          }
        >
          <Section alignItems="start" gap={0.5}>
            <Text text03>
              {t("admin.llm.deleteProviderBodyPrefix")} <b>{provider.name}</b>{" "}
              {t("admin.llm.deleteProviderBodySuffix")}
            </Text>
            {isLastProvider && (
              <Text text03>
                {t("admin.llm.connectAnotherProvider")}
              </Text>
            )}
          </Section>
        </ConfirmationModalLayout>
      )}

      <Hoverable.Root group="ExistingProviderCard">
        <Card padding={0.5}>
          <ContentAction
            icon={getProviderIcon(provider.provider)}
            title={provider.name}
            description={getProviderDisplayName(provider.provider)}
            sizePreset="main-content"
            variant="section"
            tag={
              isDefault
                ? { title: t("admin.llm.defaultTag"), color: "blue" }
                : undefined
            }
            rightChildren={
              <Section flexDirection="row" gap={0} alignItems="start">
                <Hoverable.Item
                  group="ExistingProviderCard"
                  variant="opacity-on-hover"
                >
                  <Button
                    icon={SvgTrash}
                    prominence="tertiary"
                    aria-label={t("admin.llm.deleteProviderAria")}
                    onClick={() => deleteModal.toggle(true)}
                  />
                </Hoverable.Item>
                <Button
                  icon={SvgSettings}
                  prominence="tertiary"
                  aria-label={t("admin.llm.editProviderAria")}
                  onClick={() => setIsOpen(true)}
                />
              </Section>
            }
          />
          {getModalForExistingProvider(provider, isOpen, setIsOpen)}
        </Card>
      </Hoverable.Root>
    </>
  );
}

// ============================================================================
// NewProviderCard — card for the "Add Provider" list
// ============================================================================

interface NewProviderCardProps {
  provider: WellKnownLLMProviderDescriptor;
  isFirstProvider: boolean;
  formFn: (
    shouldMarkAsDefault: boolean,
    open: boolean,
    onOpenChange: (open: boolean) => void
  ) => React.ReactNode;
}

function NewProviderCard({
  provider,
  isFirstProvider,
  formFn,
}: NewProviderCardProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Card variant="secondary" padding={0.5}>
      <ContentAction
        icon={getProviderIcon(provider.name)}
        title={getProviderProductName(provider.name)}
        description={getProviderDisplayName(provider.name)}
        sizePreset="main-content"
        variant="section"
        rightChildren={
          <Button
            rightIcon={SvgArrowExchange}
            prominence="tertiary"
            onClick={() => setIsOpen(true)}
          >
            {t("modals.connect")}
          </Button>
        }
      />
      {formFn(isFirstProvider, isOpen, setIsOpen)}
    </Card>
  );
}

// ============================================================================
// NewCustomProviderCard — card for adding a custom LLM provider
// ============================================================================

interface NewCustomProviderCardProps {
  isFirstProvider: boolean;
}

function NewCustomProviderCard({
  isFirstProvider,
}: NewCustomProviderCardProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Card variant="secondary" padding={0.5}>
      <ContentAction
        icon={getProviderIcon("custom")}
        title={getProviderProductName("custom")}
        description={getProviderDisplayName("custom")}
        sizePreset="main-content"
        variant="section"
        rightChildren={
          <Button
            rightIcon={SvgArrowExchange}
            prominence="tertiary"
            onClick={() => setIsOpen(true)}
          >
            {t("admin.llm.setUp")}
          </Button>
        }
      />
      <CustomModal
        shouldMarkAsDefault={isFirstProvider}
        open={isOpen}
        onOpenChange={setIsOpen}
      />
    </Card>
  );
}

// ============================================================================
// ApiKeyProviderCard — card for configured cloud (API-key) providers
// ============================================================================

interface ApiKeyProviderCardProps {
  provider: ApiKeyProvider;
  onDeleted: () => void;
}

function ApiKeyProviderCard({ provider, onDeleted }: ApiKeyProviderCardProps) {
  const { t } = useTranslation();
  const deleteModal = useCreateModal();
  const [editOpen, setEditOpen] = useState(false);

  const handleDelete = async () => {
    try {
      const res = await fetch(`/api/admin/user-providers/${provider.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
      toast({ message: t("admin.llm.providerDeletedSuccess") });
      deleteModal.toggle(false);
      onDeleted();
    } catch {
      toast({ message: t("admin.llm.failedToDeleteProvider"), level: "error" });
    }
  };

  return (
    <>
      {deleteModal.isOpen && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("admin.llm.deleteProviderTitle", { name: provider.name })}
          onClose={() => deleteModal.toggle(false)}
          submit={
            <Button variant="danger" onClick={handleDelete}>
              {t("sidebar.delete")}
            </Button>
          }
        >
          <Section alignItems="start" gap={0.5}>
            <Text text03>
              {t("admin.llm.deleteProviderBodyPrefix")} <b>{provider.name}</b>{" "}
              {t("admin.llm.deleteProviderBodySuffix")}
            </Text>
          </Section>
        </ConfirmationModalLayout>
      )}

      <Hoverable.Root group={`cloud-provider-${provider.id}`}>
        <Card padding={0.5}>
          <ContentAction
            icon={getProviderIcon(provider.provider_type)}
            title={provider.name}
            description={`${provider.provider_type} · ${provider.user_config.default_model ?? t("admin.llm.noDefault")}`}
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <Section flexDirection="row" gap={0} alignItems="start">
                <Hoverable.Item group={`cloud-provider-${provider.id}`} variant="opacity-on-hover">
                  <Button
                    icon={SvgSettings}
                    prominence="tertiary"
                    aria-label={t("admin.llm.editProviderAria")}
                    onClick={() => setEditOpen(true)}
                  />
                </Hoverable.Item>
                <Hoverable.Item group={`cloud-provider-${provider.id}`} variant="opacity-on-hover">
                  <Button
                    icon={SvgTrash}
                    prominence="tertiary"
                    aria-label={t("admin.llm.deleteProviderAria")}
                    onClick={() => deleteModal.toggle(true)}
                  />
                </Hoverable.Item>
              </Section>
            }
          />
        </Card>
      </Hoverable.Root>

      <EditProviderModal
        provider={provider}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
    </>
  );
}

// ============================================================================
// LLMConfigurationPage — main page component
// ============================================================================

export default function LLMConfigurationPage() {
  const { t } = useTranslation();
  const { updateUserDefaultModel, user } = useUser();
  const { llmProviders: existingLlmProviders, defaultText } =
    useAdminLLMProviders();
  const { wellKnownLLMProviders } = useWellKnownLLMProviders();
  const { providers: allProviders } = useAllProviders();
  const { llmProviders: availableModels } = useAvailableModels();

  // New DB-based providers
  const { data: urlProviders = [] } = useUrlProviders();
  const { data: apiKeyProviders = [], mutate: mutateApiKeyProviders } = useApiKeyProviders();
  const { data: wellKnownLangChainProviders = [] } = useWellKnownLangChainProviders();
  const builtinProviders = allProviders?.builtin ?? [];

  const [urlProviderModalOpen, setUrlProviderModalOpen] = useState(false);
  const [apiKeyProviderModalOpen, setApiKeyProviderModalOpen] = useState(false);
  const [downloadModalOpen, setDownloadModalOpen] = useState(false);
  const [selectedProviderForDownload, setSelectedProviderForDownload] = useState<string | null>(null);

  const knownModelsByProviderType = useMemo(
    () =>
      new Map(
        wellKnownLangChainProviders.map((provider) => [
          provider.provider_type,
          provider.known_models?.map((model) => model.name) ?? [],
        ])
      ),
    [wellKnownLangChainProviders]
  );

  const allDbProviderGroups = useMemo(
    () =>
      (availableModels ?? [])
        .map((p) => ({
          providerKey: p.id,
          providerName: p.name,
          providerType: p.provider,
          models: (p.model_configurations ?? [])
            .filter((m) => m.is_visible !== false)
            .map((m) => m.name),
        }))
        .filter((g) => g.models.length > 0),
    [availableModels]
  );

  if (!availableModels) {
    return <ThreeDotsLoader />;
  }

  // Default model/provider comes from user settings.
  // Preferred format is separate fields: default_model + default_provider_id.
  // Older data may still be stored as "providerId:modelName" in default_model.
  const currentDefaultValue = user?.preferences?.default_model ?? undefined;
  const currentDefaultProviderId = user?.preferences?.default_provider_id;

  let selectedDefaultProviderKey: string | number | undefined =
    currentDefaultProviderId ?? undefined;
  let selectedDefaultModelName: string | undefined = currentDefaultValue;

  if (currentDefaultValue && !selectedDefaultProviderKey) {
    const firstColonIndex = currentDefaultValue.indexOf(":");
    if (firstColonIndex > 0) {
      const possibleProviderKey = currentDefaultValue.slice(0, firstColonIndex);
      const hasMatchingProviderKey = allDbProviderGroups.some(
        (group) => String(group.providerKey) === possibleProviderKey
      );

      // Legacy composite value: "providerId:modelName"
      if (hasMatchingProviderKey) {
        selectedDefaultProviderKey = possibleProviderKey;
        selectedDefaultModelName = currentDefaultValue.slice(firstColonIndex + 1);
      }
    }
  }

  // If provider is still unknown, infer from model name.
  if (!selectedDefaultProviderKey && selectedDefaultModelName) {
    const matchingProvider = allDbProviderGroups.find((group) =>
      group.models.includes(selectedDefaultModelName as string)
    );
    if (matchingProvider) {
      selectedDefaultProviderKey = matchingProvider.providerKey;
    }
  }

  // For display purposes
  const selectedDefaultProviderType = selectedDefaultProviderKey
    ? allDbProviderGroups.find((group) => group.providerKey === selectedDefaultProviderKey)?.providerType
    : undefined;
  const SelectedDefaultProviderIcon = selectedDefaultProviderType
    ? getProviderIcon(selectedDefaultProviderType)
    : null;

  // Create the composite value for the dropdown (providerId:modelName)
  const dropdownCurrentValue = selectedDefaultProviderKey && selectedDefaultModelName
    ? `${selectedDefaultProviderKey}:${selectedDefaultModelName}`
    : undefined;

  async function handleDefaultModelChange(compositeValue: string) {
    try {
      if (compositeValue) {
        const separatorIndex = compositeValue.indexOf(":");
        const providerId =
          separatorIndex >= 0 ? compositeValue.slice(0, separatorIndex) : null;
        const justModelName =
          separatorIndex >= 0
            ? compositeValue.slice(separatorIndex + 1)
            : compositeValue;
        await updateUserDefaultModel(justModelName || null, providerId);
      } else {
        await updateUserDefaultModel(null, null);
      }
      toast({ message: t("admin.llm.defaultModelUpdatedSuccess") });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      toast({ message: t("admin.llm.setDefaultModelFailed", { message }), level: "error" });
    }
  }

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        separator
      />

      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.llm.workspaceTitle", {
            defaultValue: "Model provider workspace",
          })}
          description={t("admin.llm.workspaceDescription", {
            defaultValue:
              "Manage built-in, local, and cloud model providers, then choose the default model users start from.",
          })}
          metrics={[
            {
              label: t("admin.llm.builtInProvidersTitle"),
              value: String(builtinProviders.length),
            },
            {
              label: t("admin.llm.localProvidersTitle"),
              value: String(urlProviders.length),
              tone: urlProviders.length > 0 ? "success" : "neutral",
            },
            {
              label: t("admin.llm.cloudProvidersTitle"),
              value: String(apiKeyProviders.length),
              tone: apiKeyProviders.length > 0 ? "success" : "neutral",
            },
          ]}
          actions={[
            {
              label: t("admin.navigation.routes.chatPreferences.sidebar", {
                defaultValue: "Chat Preferences",
              }),
              href: ADMIN_PATHS.CHAT_PREFERENCES,
            },
            {
              label: t("admin.navigation.routes.imageGeneration.sidebar"),
              href: ADMIN_PATHS.IMAGE_GENERATION,
              primary: true,
            },
          ]}
        />
        {allDbProviderGroups.length > 0 ? (
          <Card>
            <HorizontalInput
              title={t("admin.llm.defaultModelLabel")}
              description={t("admin.llm.defaultModelDescription")}
              nonInteractive
              center
            >
              <InputSelect
                value={dropdownCurrentValue}
                onValueChange={handleDefaultModelChange}
              >
                <InputSelect.Trigger
                  placeholder={t("admin.llm.selectDefaultModelPlaceholder")}
                >
                  {dropdownCurrentValue && selectedDefaultModelName ? (
                    <span className="inline-flex items-center gap-2 text-text-04">
                      {SelectedDefaultProviderIcon && (
                        <SelectedDefaultProviderIcon className="h-4 w-4 text-text-04" />
                      )}
                      <span className="truncate">{selectedDefaultModelName}</span>
                    </span>
                  ) : null}
                </InputSelect.Trigger>
                <InputSelect.Content>
                  {allDbProviderGroups.map(
                    ({ providerKey, providerName, providerType, models }) => {
                      const ProviderIcon = getProviderIcon(providerType);

                      return (
                        <InputSelect.Group key={providerKey}>
                          <InputSelect.Label>
                            <span className="inline-flex items-center gap-2">
                              <ProviderIcon className="h-3.5 w-3.5" />
                              <span>{providerName}</span>
                            </span>
                          </InputSelect.Label>
                          {models.map((model) => (
                            <InputSelect.Item key={`${providerKey}:${model}`} value={`${providerKey}:${model}`}>
                              {model}
                            </InputSelect.Item>
                          ))}
                        </InputSelect.Group>
                      );
                    }
                  )}
                </InputSelect.Content>
              </InputSelect>
            </HorizontalInput>
          </Card>
        ) : (
          <Message
            info
            large
            icon
            close={false}
            text={t("admin.llm.setUpProviderToStart")}
            className="w-full"
          />
        )}

        {/* ── Built-in Providers (read-only) ── */}
        <GeneralLayouts.Section
          gap={0.75}
          height="fit"
          alignItems="stretch"
          justifyContent="start"
        >
          <Content
            title={t("admin.llm.builtInProvidersTitle")}
            description={t("admin.llm.builtInProvidersDescription")}
            sizePreset="main-content"
            variant="section"
          />
          <div className="flex flex-col gap-2">
            {builtinProviders.length > 0 ? (
              builtinProviders.map((provider) =>
                provider.provider_type === "ollama" ? (
                  <BuiltinOllamaPanel
                    key={`builtin-${provider.id}`}
                    onDownload={() => {
                      setSelectedProviderForDownload("builtin");
                      setDownloadModalOpen(true);
                    }}
                  />
                ) : (
                  <UrlProviderCard
                    key={`builtin-${provider.id}`}
                    provider={provider}
                    readOnly
                  />
                )
              )
            ) : (
              <Card>
                <ContentAction
                  icon={getProviderIcon("ollama_chat")}
                  title={t("admin.llm.ollamaBuiltInTitle")}
                  description={t("admin.llm.configuredFromEnvironment")}
                  sizePreset="main-content"
                  variant="section"
                />
              </Card>
            )}
          </div>
        </GeneralLayouts.Section>

        <Separator noPadding />

        {/* ── Local / Self-Hosted Providers (URL-based from DB) ── */}
        <GeneralLayouts.Section
          gap={0.75}
          height="fit"
          alignItems="stretch"
          justifyContent="start"
        >
          <div className="flex justify-between items-center">
            <Content
              title={t("admin.llm.localProvidersTitle")}
              description={t("admin.llm.localProvidersDescription")}
              sizePreset="main-content"
              variant="section"
            />
            <Button prominence="primary" onClick={() => setUrlProviderModalOpen(true)}>
              {t("admin.llm.addProviderCta")}
            </Button>
          </div>
          
          {urlProviders.length === 0 ? (
            <Text secondaryBody>{t("admin.llm.noLocalProvidersYet")}</Text>
          ) : (
            <div className="flex flex-col gap-2">
              {urlProviders.map((provider: UrlBasedProvider) => (
                <UrlProviderCard
                  key={provider.id}
                  provider={provider}
                  onDownload={(id) => {
                    setSelectedProviderForDownload(id);
                    setDownloadModalOpen(true);
                  }}
                />
              ))}
            </div>
          )}
        </GeneralLayouts.Section>

        <UrlProviderModal
          open={urlProviderModalOpen}
          onOpenChange={setUrlProviderModalOpen}
          wellKnownProviders={wellKnownLangChainProviders}
        />

        {selectedProviderForDownload && (
          <ModelDownloadModal
            open={downloadModalOpen}
            onOpenChange={setDownloadModalOpen}
            providerId={selectedProviderForDownload}
          />
        )}

        <Separator noPadding />

        {/* ── Cloud Providers (API-key-based from DB) ── */}
        <GeneralLayouts.Section
          gap={0.75}
          height="fit"
          alignItems="stretch"
          justifyContent="start"
        >
          <div className="flex justify-between items-center">
            <Content
              title={t("admin.llm.cloudProvidersTitle")}
              description={t("admin.llm.cloudProvidersDescription")}
              sizePreset="main-content"
              variant="section"
            />
            <Button prominence="primary" onClick={() => setApiKeyProviderModalOpen(true)}>
              {t("admin.llm.addProviderCta")}
            </Button>
          </div>

          {apiKeyProviders.length === 0 ? (
            <Text secondaryBody>{t("admin.llm.noCloudProvidersYet")}</Text>
          ) : (
            <div className="flex flex-col gap-2">
              {apiKeyProviders.map((provider: ApiKeyProvider) => (
                <ApiKeyProviderCard
                  key={provider.id}
                  provider={provider}
                  onDeleted={mutateApiKeyProviders}
                />
              ))}
            </div>
          )}
        </GeneralLayouts.Section>

        <ApiKeyProviderModal
          open={apiKeyProviderModalOpen}
          onOpenChange={setApiKeyProviderModalOpen}
          wellKnownProviders={wellKnownLangChainProviders}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
