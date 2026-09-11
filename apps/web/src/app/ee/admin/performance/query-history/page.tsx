"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import { QueryHistoryTable } from "@/app/ee/admin/performance/query-history/QueryHistoryTable";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.QUERY_HISTORY]!;

export default function QueryHistoryPage() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
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
        separator
      />

      <SettingsLayouts.Body>
        <QueryHistoryTable />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
