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

export default function Status() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.INDEXING_STATUS]!;
  const { datasources, isLoading, mutate } = useAirbyteDatasources();
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
            d.connector_display_name.toLowerCase().includes(search.toLowerCase())
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
        title={route.title}
        rightChildren={
          <Button href="/admin/add-connector">{t("admin.indexingStatus.addConnector")}</Button>
        }
        separator
      />
      <SettingsLayouts.Body>
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
            <Text as="span" secondaryBody>{t("admin.indexingStatus.expandAll")}</Text>
          </button>
          <button
            onClick={collapseAll}
            className="flex items-center gap-1 text-sm text-link hover:underline"
          >
            <FiChevronRight size={16} />
            <Text as="span" secondaryBody>{t("admin.indexingStatus.collapseAll")}</Text>
          </button>
        </div>

        {isLoading && (
          <Text as="p" secondaryBody className="text-center py-8">
            {t("admin.indexingStatus.loading")}
          </Text>
        )}

        {!isLoading && groups.length === 0 && (
          <Text as="p" secondaryBody className="text-center py-8">
            {t("admin.indexingStatus.noDataSources")}{" "}
            <a href="/admin/add-connector" className="text-link underline">
              {t("admin.indexingStatus.addConnectorLinkText")}
            </a>{" "}
            {t("admin.indexingStatus.toGetStarted")}
          </Text>
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
