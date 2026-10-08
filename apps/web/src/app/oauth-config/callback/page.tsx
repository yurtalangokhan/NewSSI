"use client";

import OAuthCallbackPage from "@/components/oauth/OAuthCallbackPage";
import { useTranslation } from "react-i18next";
import { completeOAuthConfigCallback } from "@/lib/api/domains/integrations/api";

export default function OAuthConfigCallbackPage() {
  const { t } = useTranslation("common", { keyPrefix: "auth" });

  return (
    <OAuthCallbackPage
      config={{
        callback: completeOAuthConfigCallback,
        defaultRedirectPath: "/app",
        processingMessage: t("oauthCallback.oauthConfigProcessing"),
        processingDetails: t("oauthCallback.oauthConfigProcessingDetails"),
        successMessage: t("oauthCallback.oauthConfigSuccess"),
        successDetailsTemplate: t("oauthCallback.oauthConfigSuccessDetail"),
        errorMessage: t("oauthCallback.oauthConfigError"),
        backButtonText: t("oauthCallback.backToChat"),
        autoRedirectDelay: 2000,
      }}
    />
  );
}
