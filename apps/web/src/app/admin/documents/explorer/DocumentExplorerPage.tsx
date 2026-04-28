"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { Explorer } from "./Explorer";
import { Connector } from "@/lib/connectors/connectors";
import { DocumentSetSummary } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface DocumentExplorerPageProps {
  initialSearchValue: string | undefined;
  connectors: Connector<any>[];
  documentSets: DocumentSetSummary[];
}

export default function DocumentExplorerPage({
  initialSearchValue,
  connectors,
  documentSets,
}: DocumentExplorerPageProps) {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_EXPLORER]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        separator
      />

      <SettingsLayouts.Body>
        <Explorer
          initialSearchValue={initialSearchValue}
          connectors={connectors}
          documentSets={documentSets}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
