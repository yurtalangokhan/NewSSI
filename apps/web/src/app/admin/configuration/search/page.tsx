"use client";

import { ThreeDotsLoader } from "@/components/Loading";
import { errorHandlingFetcher } from "@/lib/fetcher";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import Button from "@/refresh-components/buttons/Button";
import useSWR from "swr";
import { ModelPreview } from "@/components/embedding/ModelSelector";
import {
  HostedEmbeddingModel,
  CloudEmbeddingModel,
} from "@/components/embedding/interfaces";
import { SavedSearchSettings } from "@/app/admin/embeddings/interfaces";
import UpgradingPage from "./UpgradingPage";
import { useContext } from "react";
import { SettingsContext } from "@/providers/SettingsProvider";
import CardSection from "@/components/admin/CardSection";
import { ErrorCallout } from "@/components/ErrorCallout";
import { useToastFromQuery } from "@/hooks/useToast";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.SEARCH_SETTINGS]!;

export interface EmbeddingDetails {
  api_key: string;
  custom_config: any;
  default_model_id?: number;
  name: string;
}

function Main() {
  const { t } = useTranslation();
  const settings = useContext(SettingsContext);
  useToastFromQuery({
    "search-settings": {
      message: t("admin.search.changedSuccessfully"),
      type: "success",
    },
  });
  const {
    data: currentEmeddingModel,
    isLoading: isLoadingCurrentModel,
    error: currentEmeddingModelError,
  } = useSWR<CloudEmbeddingModel | HostedEmbeddingModel | null>(
    "/api/search-settings/get-current-search-settings",
    errorHandlingFetcher,
    { refreshInterval: 5000 } // 5 seconds
  );

  const { data: searchSettings, isLoading: isLoadingSearchSettings } =
    useSWR<SavedSearchSettings | null>(
      "/api/search-settings/get-current-search-settings",
      errorHandlingFetcher,
      { refreshInterval: 5000 } // 5 seconds
    );

  const {
    data: futureEmbeddingModel,
    isLoading: isLoadingFutureModel,
    error: futureEmeddingModelError,
  } = useSWR<CloudEmbeddingModel | HostedEmbeddingModel | null>(
    "/api/search-settings/get-secondary-search-settings",
    errorHandlingFetcher,
    { refreshInterval: 5000 } // 5 seconds
  );

  if (
    isLoadingCurrentModel ||
    isLoadingFutureModel ||
    isLoadingSearchSettings
  ) {
    return <ThreeDotsLoader />;
  }

  if (
    currentEmeddingModelError ||
    !currentEmeddingModel ||
    futureEmeddingModelError
  ) {
    return <ErrorCallout errorTitle={t("admin.search.fetchEmbeddingModelError")} />;
  }

  return (
    <div>
      {!futureEmbeddingModel ? (
        <>
          {settings?.settings.needs_reindexing && (
            <p className="max-w-3xl">
              {t("admin.search.reindexWarning")}
            </p>
          )}
          <Title className="mb-6 mt-8 !text-2xl">{t("admin.search.embeddingModelTitle")}</Title>

          {currentEmeddingModel ? (
            <ModelPreview model={currentEmeddingModel} display showDetails />
          ) : (
            <Title className="mt-8 mb-4">{t("admin.search.chooseEmbeddingModel")}</Title>
          )}

          <Title className="mb-2 mt-8 !text-2xl">{t("admin.search.postProcessingTitle")}</Title>

          <CardSection className="!mr-auto mt-8 !w-96 shadow-lg bg-background-tint-00 rounded-16">
            {searchSettings && (
              <>
                <div className="px-1 w-full rounded-lg">
                  <div className="space-y-4">
                    <div>
                      <Text className="font-semibold">{t("admin.search.multipassIndexing")}</Text>
                      <Text className="text-text-700">
                        {searchSettings.multipass_indexing
                          ? t("admin.search.enabled")
                          : t("admin.search.disabled")}
                      </Text>
                    </div>

                    <div>
                      <Text className="font-semibold">{t("admin.search.contextualRag")}</Text>
                      <Text className="text-text-700">
                        {searchSettings.enable_contextual_rag
                          ? t("admin.search.enabled")
                          : t("admin.search.disabled")}
                      </Text>
                    </div>
                  </div>
                </div>
              </>
            )}
          </CardSection>

          <div className="mt-4">
            <Button action href="/admin/embeddings">
              {t("admin.search.updateButton")}
            </Button>
          </div>
        </>
      ) : (
        <UpgradingPage futureEmbeddingModel={futureEmbeddingModel} />
      )}
    </div>
  );
}

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        title={t(route.titleKey || "", { defaultValue: route.title })}
        icon={route.icon}
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.search.workspaceTitle", {
            defaultValue: "Search quality workspace",
          })}
          description={t("admin.search.workspaceDescription", {
            defaultValue:
              "Review embedding configuration, reindexing needs, and the retrieval settings that shape answer quality.",
          })}
          metrics={[
            {
              label: t("admin.search.embeddingLabel", {
                defaultValue: "Embedding model",
              }),
              value: t("admin.search.configurable", {
                defaultValue: "Configurable",
              }),
            },
            {
              label: t("admin.search.indexHealthLabel", {
                defaultValue: "Index health",
              }),
              value: t("admin.search.reviewBelow", {
                defaultValue: "Review below",
              }),
              tone: "warning",
            },
            {
              label: t("admin.search.relatedContentLabel", {
                defaultValue: "Related content",
              }),
              value: t("admin.navigation.routes.documentProcessing.sidebar", {
                defaultValue: "Document Processing",
              }),
            },
          ]}
          actions={[
            {
              label: t("admin.navigation.routes.documentProcessing.sidebar", {
                defaultValue: "Document Processing",
              }),
              href: ADMIN_PATHS.DOCUMENT_PROCESSING,
            },
            {
              label: t("admin.search.updateButton", {
                defaultValue: "Update",
              }),
              href: "/admin/embeddings",
              primary: true,
            },
          ]}
        />
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
