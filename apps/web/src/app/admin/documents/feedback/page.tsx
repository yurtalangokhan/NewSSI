"use client";

import { notFound } from "next/navigation";
import { LoadingAnimation } from "@/components/Loading";
import { useMostReactedToDocuments } from "@/lib/hooks";
import { DocumentFeedbackTable } from "./DocumentFeedbackTable";
import { numPages, numToDisplay } from "./constants";
import Title from "@/components/ui/title";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

function Main() {
  const { t } = useTranslation();
  const {
    data: mostLikedDocuments,
    isLoading: isMostLikedDocumentsLoading,
    error: mostLikedDocumentsError,
    refreshDocs: refreshMostLikedDocuments,
  } = useMostReactedToDocuments(false, numToDisplay * numPages);

  const {
    data: mostDislikedDocuments,
    isLoading: isMostLikedDocumentLoading,
    error: mostDislikedDocumentsError,
    refreshDocs: refreshMostDislikedDocuments,
  } = useMostReactedToDocuments(true, numToDisplay * numPages);

  const refresh = () => {
    refreshMostLikedDocuments();
    refreshMostDislikedDocuments();
  };

  if (isMostLikedDocumentsLoading || isMostLikedDocumentLoading) {
    return <LoadingAnimation text={t("admin.documentsFeedback.loading")} />;
  }

  if (
    mostLikedDocumentsError ||
    mostDislikedDocumentsError ||
    !mostLikedDocuments ||
    !mostDislikedDocuments
  ) {
    return (
      <div className="text-red-600">
        {t("admin.documentsFeedback.errorLoadingDocuments")} -{" "}
        {mostDislikedDocumentsError || mostLikedDocumentsError}
      </div>
    );
  }

  return (
    <div>
      <Title className="mb-2">
        {t("admin.documentsFeedback.mostLikedTitle")}
      </Title>
      <DocumentFeedbackTable documents={mostLikedDocuments} refresh={refresh} />

      <Title className="mb-2 mt-6">
        {t("admin.documentsFeedback.mostDislikedTitle")}
      </Title>
      <DocumentFeedbackTable
        documents={mostDislikedDocuments}
        refresh={refresh}
      />
    </div>
  );
}

export default function Page() {
  notFound();

  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_FEEDBACK]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header icon={route.icon} title={route.title} separator />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.documentsFeedback.workspaceTitle", {
            defaultValue: "Document feedback workspace",
          })}
          description={t("admin.documentsFeedback.workspaceDescription", {
            defaultValue:
              "Review highly liked and disliked documents so retrieval quality improvements have a clear starting point.",
          })}
          metrics={[
            {
              label: t("admin.documentsFeedback.positiveSignalLabel", {
                defaultValue: "Positive signal",
              }),
              value: t("admin.documentsFeedback.mostLikedTitle"),
              tone: "success",
            },
            {
              label: t("admin.documentsFeedback.negativeSignalLabel", {
                defaultValue: "Negative signal",
              }),
              value: t("admin.documentsFeedback.mostDislikedTitle"),
              tone: "warning",
            },
            {
              label: t("admin.documentsFeedback.nextStepLabel", {
                defaultValue: "Next step",
              }),
              value: t("admin.navigation.routes.documentExplorer.sidebar", {
                defaultValue: "Explorer",
              }),
            },
          ]}
          actions={[
            {
              label: t("admin.navigation.routes.documentExplorer.sidebar", {
                defaultValue: "Explorer",
              }),
              href: ADMIN_PATHS.DOCUMENT_EXPLORER,
            },
            {
              label: t("admin.navigation.routes.searchSettings.sidebar", {
                defaultValue: "Search Settings",
              }),
              href: ADMIN_PATHS.SEARCH_SETTINGS,
              primary: true,
            },
          ]}
        />
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
