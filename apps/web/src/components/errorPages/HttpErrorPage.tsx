"use client";

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

const errorContent = {
  400: {
    title: "Bad request",
    label: "400",
    description:
      "The request could not be understood. Check the link and try again.",
    Icon: SvgAlertTriangle,
    iconClassName: "stroke-status-warning-05",
  },
  401: {
    title: "Unauthorized",
    label: "401",
    description:
      "Your session could not be verified. Sign in again to continue.",
    Icon: SvgLock,
    iconClassName: "stroke-status-error-05",
  },
  403: {
    title: "Access denied",
    label: "403",
    description:
      "You do not have permission to open this area. Ask an administrator if access is required.",
    Icon: SvgShield,
    iconClassName: "stroke-status-error-05",
  },
  404: {
    title: "Page not found",
    label: "404",
    description:
      "This page does not exist or may have moved. Return to the app and choose a valid destination.",
    Icon: SvgSearch,
    iconClassName: "stroke-text-04",
  },
  500: {
    title: "Something went wrong",
    label: "500",
    description: "The app hit an unexpected problem. Try again in a moment.",
    Icon: SvgAlertCircle,
    iconClassName: "stroke-status-error-05",
  },
} as const;

export type HttpErrorCode = keyof typeof errorContent;

interface HttpErrorPageProps {
  code: HttpErrorCode;
}

export const HTTP_ERROR_CODES = Object.keys(errorContent).map(Number);

export function isHttpErrorCode(code: number): code is HttpErrorCode {
  return code in errorContent;
}

export default function HttpErrorPage({ code }: HttpErrorPageProps) {
  const content = errorContent[code];
  const Icon = content.Icon;
  const isAuthError = code === 401;

  return (
    <ErrorPageLayout>
      <div className="flex flex-col gap-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-2">
            <Text as="p" figureSmallLabel text03>
              HTTP {content.label}
            </Text>
            <Text as="p" headingH2 text05>
              {content.title}
            </Text>
          </div>

          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-08 border border-border bg-background-neutral-02">
            <Icon className={`h-6 w-6 ${content.iconClassName}`} />
          </div>
        </div>

        <Text as="p" text03>
          {content.description}
        </Text>

        <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row">
          <Button
            href={isAuthError ? "/auth/login" : "/app"}
            leftIcon={isAuthError ? SvgLock : SvgArrowLeft}
          >
            {isAuthError ? "Sign in" : "Back to app"}
          </Button>
          <Button secondary href="/">
            Home
          </Button>
        </div>
      </div>
    </ErrorPageLayout>
  );
}
