"use client";

import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SvgChevronDown, SvgChevronRight } from "@opal/icons";
import Button from "@/refresh-components/buttons/Button";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import { useTranslation } from "react-i18next";
import { getErrorIcon, getErrorTitle } from "./errorHelpers";
import Text from "@/refresh-components/texts/Text";

interface ResubmitProps {
  resubmit: () => void;
}

export const Resubmit: React.FC<ResubmitProps> = ({ resubmit }) => {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center gap-y-2 mt-4">
      <Text as="p" className="text-sm text-neutral-700 dark:text-neutral-300">
        {t("resubmit.errorMessage")}
      </Text>
      <Button onClick={resubmit}>{t("resubmit.regenerateButton")}</Button>
    </div>
  );
};

export const ErrorBanner = ({
  error,
  errorCode,
  isRetryable = true,
  details,
  stackTrace,
  resubmit,
}: {
  error: string;
  errorCode?: string;
  isRetryable?: boolean;
  details?: Record<string, any>;
  stackTrace?: string | null;
  resubmit?: () => void;
}) => {
  const { t } = useTranslation();
  const [isStackTraceExpanded, setIsStackTraceExpanded] = useState(false);

  return (
    <div className="text-red-700 mt-4 text-sm my-auto">
      <Alert variant="broken">
        {getErrorIcon(errorCode)}
        <AlertTitle>{getErrorTitle(errorCode, t)}</AlertTitle>
        <AlertDescription className="flex flex-col gap-y-1">
          <span>{error}</span>
          {details?.model && (
            <span className="text-xs text-muted-foreground">
              {t("resubmit.modelLabel", { model: details.model })}
              {details.provider && ` (${details.provider})`}
            </span>
          )}
          {details?.tool_name && (
            <span className="text-xs text-muted-foreground">
              {t("resubmit.toolLabel", { tool: details.tool_name })}
            </span>
          )}
          {stackTrace && (
            <div className="mt-2 border-t border-neutral-200 dark:border-neutral-700 pt-2">
              <div className="flex flex-1 items-center justify-between">
                <Button
                  tertiary
                  leftIcon={
                    isStackTraceExpanded ? SvgChevronDown : SvgChevronRight
                  }
                  onClick={() => setIsStackTraceExpanded(!isStackTraceExpanded)}
                >
                  {t("resubmit.stackTrace")}
                </Button>
                <CopyIconButton
                  prominence="tertiary"
                  getCopyText={() => stackTrace}
                />
              </div>
              {isStackTraceExpanded && (
                <pre className="mt-2 p-3 bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded text-xs text-neutral-700 dark:text-neutral-300 overflow-auto max-h-48 whitespace-pre-wrap font-mono">
                  {stackTrace}
                </pre>
              )}
            </div>
          )}
        </AlertDescription>
      </Alert>
      {isRetryable && resubmit && <Resubmit resubmit={resubmit} />}
    </div>
  );
};
