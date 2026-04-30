"use client";

import OAuthCallbackPage from "@/components/oauth/OAuthCallbackPage";
import { useTranslation } from "react-i18next";

export default function FederatedOAuthCallbackPage() {
  const { t } = useTranslation("auth");
  const federatedConfig = {
    processingMessage: t("oauthCallback.processing"),
    processingDetails: t("oauthCallback.federatedProcessingDetails"),
    successMessage: t("oauthCallback.successTitle"),
    successDetailsTemplate: t("oauthCallback.federatedSuccess"),
    errorMessage: t("oauthCallback.errorTitle"),
    backButtonText: t("oauthCallback.backToChat"),
    redirectingMessage: t("oauthCallback.federatedRedirecting"),
    autoRedirectDelay: 2000,
    defaultRedirectPath: "/app",
    callbackApiUrl: "/api/federated/callback",
    errorMessageMap: {
      "validation errors": t("oauthCallback.federatedErrorValidation"),
      client_secret: t("oauthCallback.federatedErrorClientSecret"),
      oauth: t("oauthCallback.federatedErrorOAuth"),
    },
  };

  return <OAuthCallbackPage config={federatedConfig} />;
}
