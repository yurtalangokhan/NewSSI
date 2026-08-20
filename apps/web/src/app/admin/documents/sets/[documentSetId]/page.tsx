"use client";
import { use } from "react";

import { ErrorCallout } from "@/components/ErrorCallout";
import { refreshDocumentSets, useDocumentSets } from "../hooks";
import { useConnectorStatus, useUserGroups } from "@/lib/hooks";
import { ThreeDotsLoader } from "@/components/Loading";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import CardSection from "@/components/admin/CardSection";
import { DocumentSetCreationForm } from "../DocumentSetCreationForm";
import {  useRouter , notFound } from "next/navigation";
import { useTranslation } from "react-i18next";

function Main({ documentSetId }: { documentSetId: number }) {
  const router = useRouter();

  const {
    data: documentSets,
    isLoading: isDocumentSetsLoading,
    error: documentSetsError,
  } = useDocumentSets();

  const {
    data: ccPairs,
    isLoading: isCCPairsLoading,
    error: ccPairsError,
  } = useConnectorStatus();

  // EE only
  const { data: userGroups, isLoading: userGroupsIsLoading } = useUserGroups();
  const { t } = useTranslation();

  if (isDocumentSetsLoading || isCCPairsLoading || userGroupsIsLoading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <ThreeDotsLoader />
      </div>
    );
  }

  if (documentSetsError || !documentSets) {
    return (
      <ErrorCallout
        errorTitle={t("admin.documentSets.failedToFetchDocumentSets")}
        errorMsg={documentSetsError}
      />
    );
  }

  if (ccPairsError || !ccPairs) {
    return (
      <ErrorCallout
        errorTitle={t("admin.documentSets.failedToFetchConnectors")}
        errorMsg={ccPairsError}
      />
    );
  }

  const documentSet = documentSets.find(
    (documentSet) => documentSet.id === documentSetId
  );
  if (!documentSet) {
    return (
      <ErrorCallout
        errorTitle={t("admin.documentSets.documentSetNotFound")}
        errorMsg={t("admin.documentSets.documentSetNotFoundMsg", { id: documentSetId })}
      />
    );
  }

  return (
    <CardSection>
      <DocumentSetCreationForm
        ccPairs={ccPairs}
        userGroups={userGroups}
        onClose={() => {
          refreshDocumentSets();
          router.push("/admin/documents/sets");
        }}
        existingDocumentSet={documentSet}
      />
    </CardSection>
  );
}

export default function Page(props: {
  params: Promise<{ documentSetId: string }>;
}) {
  notFound();

  const { t } = useTranslation();
  const params = use(props.params);
  const documentSetId = parseInt(params.documentSetId);
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_SETS]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t("admin.documentSets.editDocumentSetTitle")}
        separator
        backButton
      />
      <SettingsLayouts.Body>
        <Main documentSetId={documentSetId} />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
