"use client";

import { useCallback, useMemo, useState } from "react";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useToastFromQuery } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import { useAirbyteDatasources } from "@/lib/airbyte";
import {
  AirbyteDatasourceTable,
  AirbyteDatasourceGroup,
} from "./AirbyteDatasourceTable";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { FiChevronDown, FiChevronRight } from "react-icons/fi";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { ConnectorStaggeredSkeleton } from "./ConnectorRowSkeleton";
import EmptyMessage from "@/refresh-components/EmptyMessage";

export default function Status() {
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.INDEXING_STATUS]!;
  const { datasources, isLoading, mutate } = useAirbyteDatasources();
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [toggledGroups, setToggledGroups] = useState<Record<string, boolean>>(
    {}
  );

  useToastFromQuery({
    "connector-created": {
      message: t("admin.indexingStatus.connectorCreated"),
      type: "success",
    },
    "connector-deleted": {
      message: t("admin.indexingStatus.connectorDeleted"),
      type: "success",
    },
  });

  const groups = useMemo<AirbyteDatasourceGroup[]>(() => {
    const all = datasources ?? [];
    const filtered = search.trim()
      ? all.filter(
          (d) =>
            d.name.toLowerCase().includes(search.toLowerCase()) ||
            d.connector_display_name
              .toLowerCase()
              .includes(search.toLowerCase())
        )
      : all;

    const byType: Record<string, AirbyteDatasourceGroup> = {};
    for (const ds of filtered) {
      if (!byType[ds.connector_type]) {
        byType[ds.connector_type] = {
          connector_type: ds.connector_type,
          connector_display_name: ds.connector_display_name,
          datasources: [],
        };
      }
      byType[ds.connector_type]!.datasources.push(ds);
    }
    return Object.values(byType);
  }, [datasources, search]);

  const totalIndexedDocuments = useMemo(
    () =>
      (datasources ?? []).reduce((sum, d) => sum + (d.document_count ?? 0), 0),
    [datasources]
  );
  const erroredSourcesCount = useMemo(
    () => (datasources ?? []).filter((d) => d.sync_status === "error").length,
    [datasources]
  );

  const handleToggle = useCallback((key: string) => {
    setToggledGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const expandAll = useCallback(() => {
    const next: Record<string, boolean> = {};
    groups.forEach((g) => (next[g.connector_type] = true));
    setToggledGroups(next);
  }, [groups]);

  const collapseAll = useCallback(() => {
    setToggledGroups({});
  }, []);

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        rightChildren={
          <Button href="/admin/add-connector">
            {t("admin.indexingStatus.addConnector")}
          </Button>
        }
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.indexingStatus.workspaceTitle", {
            defaultValue: "Connector control room",
          })}
          description={t("admin.indexingStatus.workspaceDescription", {
            defaultValue:
              "Monitor connected sources, expand by connector type, and jump straight into adding the next data source.",
          })}
          isLoading={isLoading}
          metrics={[
            {
              label: t("admin.indexingStatus.connectedSourcesLabel", {
                defaultValue: "Connected sources",
              }),
              value: isLoading ? "..." : String(datasources?.length ?? 0),
              tone: (datasources?.length ?? 0) > 0 ? "success" : "neutral",
            },
            {
              label: t("admin.indexingStatus.connectorTypesLabel", {
                defaultValue: "Connector types",
              }),
              value: isLoading ? "..." : String(groups.length),
            },
            {
              label: t("admin.indexingStatus.totalDocumentsLabel", {
                defaultValue: "Total indexed documents",
              }),
              value: isLoading ? "..." : String(totalIndexedDocuments),
            },
            {
              label: t("admin.indexingStatus.erroredSourcesLabel", {
                defaultValue: "Sync errors",
              }),
              value: isLoading ? "..." : String(erroredSourcesCount),
              tone: erroredSourcesCount > 0 ? "warning" : "neutral",
            },
          ]}
        />
        {!isLoading && (datasources?.length ?? 0) > 0 && (
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 max-w-sm">
              <InputTypeIn
                type="search"
                placeholder={t("admin.indexingStatus.searchPlaceholder")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button
              onClick={expandAll}
              className="flex items-center gap-1 text-sm text-link hover:underline"
            >
              <FiChevronDown size={16} />
              <Text as="span" secondaryBody>
                {t("admin.indexingStatus.expandAll")}
              </Text>
            </button>
            <button
              onClick={collapseAll}
              className="flex items-center gap-1 text-sm text-link hover:underline"
            >
              <FiChevronRight size={16} />
              <Text as="span" secondaryBody>
                {t("admin.indexingStatus.collapseAll")}
              </Text>
            </button>
          </div>
        )}

        {isLoading && (
          <div className="w-full mt-2">
            <ConnectorStaggeredSkeleton standalone={true} rowCount={4} />
          </div>
        )}

        {!isLoading && (datasources?.length ?? 0) === 0 && (
          <EmptyMessage
            icon={route.icon}
            title={t("admin.indexingStatus.noDataSources")}
            description={t("admin.indexingStatus.noDataSourcesDescription", {
              defaultValue:
                "Ajanlarınız için belge indekslemeye başlamak üzere yeni bir veri kaynağı bağlayın.",
            })}
          >
            <div>
              <Button href="/admin/add-connector" secondary size="md">
                {t("admin.indexingStatus.addConnector")}
              </Button>
            </div>
          </EmptyMessage>
        )}

        {!isLoading &&
          (datasources?.length ?? 0) > 0 &&
          groups.length === 0 && (
            <EmptyMessage
              title={t("admin.indexingStatus.noMatchingDataSources", {
                defaultValue: "Eşleşen veri kaynağı bulunamadı",
              })}
              description={t(
                "admin.indexingStatus.noMatchingDataSourcesDescription",
                {
                  defaultValue:
                    "Farklı bir arama terimi veya bağlayıcı türü deneyin.",
                }
              )}
            />
          )}

        {!isLoading && groups.length > 0 && (
          <AirbyteDatasourceTable
            groups={groups}
            toggledGroups={toggledGroups}
            onToggle={handleToggle}
            onMutate={mutate}
          />
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
