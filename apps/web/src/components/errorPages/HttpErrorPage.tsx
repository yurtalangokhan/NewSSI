"use client";

import { useTranslation } from "react-i18next";
import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import {
  SvgAlertCircle,
  SvgAlertTriangle,
  SvgArrowLeft,
  SvgLock,
  SvgSearch,
  SvgShield,
} from "@opal/icons";

export type HttpErrorCode = 400 | 401 | 403 | 404 | 500;

const ERROR_ICONS: Record<HttpErrorCode, { Icon: React.ComponentType<{ className?: string }>; iconClassName: string }> = {
  400: { Icon: SvgAlertTriangle, iconClassName: "stroke-status-warning-05" },
  401: { Icon: SvgLock, iconClassName: "stroke-text-04" },
  403: { Icon: SvgShield, iconClassName: "stroke-status-danger-05" },
  404: { Icon: SvgSearch, iconClassName: "stroke-text-04" },
  500: { Icon: SvgAlertCircle, iconClassName: "stroke-status-danger-05" },
};

export default function HttpErrorPage({
  code,
  error,
}: {
  code?: HttpErrorCode;
  error?: Error & { digest?: string };
}) {
  const { t } = useTranslation();
  const resolvedCode: HttpErrorCode =
    code ??
    ((error as { status?: number })?.status as HttpErrorCode) ??
    500;
  const validCode = (resolvedCode in ERROR_ICONS ? resolvedCode : 500) as HttpErrorCode;
  const { Icon, iconClassName } = ERROR_ICONS[validCode];
  const isAuthError = validCode === 401;

  return (
    <ErrorPageLayout>
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-background-neutral-02 border border-border">
            <Icon className={`h-5 w-5 ${iconClassName}`} />
          </div>
          <div>
            <span className="text-xs font-medium text-text-03 font-mono">
              {validCode}
            </span>
            <Text as="p" headingH2 className="leading-tight">
              {t(`errors.errorPages.http.${validCode}.title`)}
            </Text>
          </div>
        </div>

        <Text as="p" text03>
          {t(`errors.errorPages.http.${validCode}.description`)}
        </Text>

        <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row">
          <Button
            href={isAuthError ? "/auth/login" : "/app"}
            leftIcon={isAuthError ? SvgLock : SvgArrowLeft}
          >
            {isAuthError ? t("errors.errorPages.signInButton") : t("errors.errorPages.backToAppButton")}
          </Button>
          <Button secondary href="/">
            {t("errors.errorPages.homeButton")}
          </Button>
        </div>
      </div>
    </ErrorPageLayout>
  );
}
