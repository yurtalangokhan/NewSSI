"use client";

import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/refresh-components/texts/Text";
import { SvgHardDrive } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import CollectionsPanel from "./components/CollectionsPanel";
import DocumentsPanel from "./components/DocumentsPanel";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_PROCESSING]!;

// ---------------------------------------------------------------------------
// RAG management section
// ---------------------------------------------------------------------------

function RagManagementSection() {
  const { t } = useTranslation();
  const [selectedCollectionId, setSelectedCollectionId] = useState<
    string | null
  >(null);
  const [selectedIsDatasource, setSelectedIsDatasource] = useState(false);

  function handleCollectionSelect(id: string | null, isDatasource?: boolean) {
    setSelectedCollectionId(id);
    setSelectedIsDatasource(isDatasource ?? false);
  }

  return (
    <div className="flex flex-col gap-4">
      <CollectionsPanel
        selectedCollectionId={selectedCollectionId}
        onCollectionSelect={handleCollectionSelect}
      />

      {selectedCollectionId ? (
        <DocumentsPanel collectionId={selectedCollectionId} readOnly={selectedIsDatasource} />
      ) : (
        <CardSection>
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <SvgHardDrive
              className="h-8 w-8 stroke-text-03 opacity-40"
              aria-hidden
            />
            <Text as="p" mainContentMuted text03>
              {t("admin.documentProcessing.selectOrCreateCollection")}
            </Text>
          </div>
        </CardSection>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        separator
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-8 pb-36">
          <div className="flex flex-col gap-2">
            <Text as="p" headingH3 text05>
              LangConnect RAG
            </Text>
            <Text as="p" mainContentBody text04 className="leading-relaxed">
              {t("admin.documentProcessing.langConnectRag")}
              {t("admin.documentProcessing.langConnectRagDescription")}
            </Text>
          </div>

          <RagManagementSection />
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
