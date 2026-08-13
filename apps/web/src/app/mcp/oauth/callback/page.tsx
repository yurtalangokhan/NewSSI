"use client";

import OAuthCallbackPage from "@/components/oauth/OAuthCallbackPage";
import { useTranslation } from "react-i18next";

export default function MCPOAuthCallbackPage() {
  const { t } = useTranslation("common", { keyPrefix: "auth" });
  const mcpConfig = {
    processingMessage: t("oauthCallback.processing"),
    processingDetails: t("oauthCallback.mcpProcessingDetails"),
    successMessage: t("oauthCallback.successTitle"),
    successDetailsTemplate: t("oauthCallback.mcpSuccess"),
    errorMessage: t("oauthCallback.errorTitle"),
    backButtonText: t("oauthCallback.backToChat"),
    redirectingMessage: t("oauthCallback.mcpRedirecting"),
    autoRedirectDelay: 2000,
    defaultRedirectPath: "/app",
    callbackApiUrl: "/api/mcp/oauth/callback",
    errorMessageMap: {
      "server not found": t("oauthCallback.mcpErrorServerNotFound"),
      credentials: t("oauthCallback.mcpErrorCredentials"),
      oauth: t("oauthCallback.mcpErrorOAuth"),
      validation: t("oauthCallback.mcpErrorValidation"),
    },
  };

  return <OAuthCallbackPage config={mcpConfig} />;
}
