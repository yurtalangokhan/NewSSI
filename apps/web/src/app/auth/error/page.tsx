"use client";

import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import Button from "@/refresh-components/buttons/Button";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "next/navigation";

import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import { APP_SUPPORT_EMAIL } from "@/lib/appInfo";
import { formatErrorMessage } from "@/components/ErrorCallout";

const Page = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const rawErrorMessage = searchParams.get("error");
  const errorMessage = rawErrorMessage
    ? formatErrorMessage(rawErrorMessage)
    : rawErrorMessage;

  return (
    <AuthFlowContainer>
      <div className="flex flex-col space-y-6 max-w-md mx-auto">
        <h2 className="text-2xl font-bold text-text-900 text-center">
          {t("authPages.authError.title")}
        </h2>
        <p className="text-text-700 text-center">
          {errorMessage || t("authPages.authError.description")}
        </p>
        {!errorMessage && (
          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-4 shadow-sm">
            <h3 className="text-red-800 dark:text-red-400 font-semibold mb-2">
              {t("authPages.authError.possibleIssuesTitle")}
            </h3>
            <ul className="space-y-2">
              <li className="flex items-center text-red-700 dark:text-red-400">
                <div className="w-2 h-2 bg-red-500 dark:bg-red-400 rounded-full mr-2"></div>
                {t("authPages.authError.issue1")}
              </li>
              <li className="flex items-center text-red-700 dark:text-red-400">
                <div className="w-2 h-2 bg-red-500 dark:bg-red-400 rounded-full mr-2"></div>
                {t("authPages.authError.issue2")}
              </li>
              <li className="flex items-center text-red-700 dark:text-red-400">
                <div className="w-2 h-2 bg-red-500 dark:bg-red-400 rounded-full mr-2"></div>
                {t("authPages.authError.issue3")}
              </li>
            </ul>
          </div>
        )}
        {errorMessage && (
          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-4 shadow-sm">
            <p className="text-red-700 dark:text-red-400 text-sm font-mono break-words">
              {errorMessage}
            </p>
          </div>
        )}

        <Button href="/auth/login" className="w-full">
          {t("authPages.authError.returnButton")}
        </Button>
        <p className="text-sm text-text-500 text-center">
          {t("authPages.authError.tryAgainNote")}
          {NEXT_PUBLIC_CLOUD_ENABLED && (
            <span className="block mt-1 text-blue-600">
              {t("authPages.authError.cloudSupportNote")}{" "}
              <a href={`mailto:${APP_SUPPORT_EMAIL}`} className="text-blue-600">
                {APP_SUPPORT_EMAIL}
              </a>
            </span>
          )}
        </p>
      </div>
    </AuthFlowContainer>
  );
};

export default Page;
