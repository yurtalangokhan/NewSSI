import { AlertCircle, Clock, Lock, Wifi, Server } from "lucide-react";

/**
 * Get the appropriate icon for a given error code
 */
export const getErrorIcon = (errorCode?: string) => {
  switch (errorCode) {
    case "RATE_LIMIT":
      return <Clock className="h-4 w-4" />;
    case "AUTH_ERROR":
    case "PERMISSION_DENIED":
      return <Lock className="h-4 w-4" />;
    case "CONNECTION_ERROR":
      return <Wifi className="h-4 w-4" />;
    case "SERVICE_UNAVAILABLE":
      return <Server className="h-4 w-4" />;
    case "BUDGET_EXCEEDED":
      return <AlertCircle className="h-4 w-4" />;
    default:
      return <AlertCircle className="h-4 w-4" />;
  }
};

/**
 * Get a human-readable title for a given error code
 */
export const getErrorTitle = (
  errorCode: string | undefined,
  t: (key: string) => string
) => {
  switch (errorCode) {
    case "RATE_LIMIT":
      return t("errors.rateLimit");
    case "AUTH_ERROR":
      return t("errors.authError");
    case "PERMISSION_DENIED":
      return t("errors.permissionDenied");
    case "CONTEXT_TOO_LONG":
      return t("errors.contextTooLong");
    case "TOOL_CALL_FAILED":
      return t("errors.toolCallFailed");
    case "CONNECTION_ERROR":
      return t("errors.connectionError");
    case "SERVICE_UNAVAILABLE":
      return t("errors.serviceUnavailable");
    case "INIT_FAILED":
      return t("errors.initFailed");
    case "VALIDATION_ERROR":
      return t("errors.validationError");
    case "BUDGET_EXCEEDED":
      return t("errors.budgetExceeded");
    case "CONTENT_POLICY":
      return t("errors.contentPolicy");
    case "BAD_REQUEST":
      return t("errors.badRequest");
    case "NOT_FOUND":
      return t("errors.notFound");
    case "API_ERROR":
      return t("errors.apiError");
    default:
      return t("errors.generic");
  }
};
