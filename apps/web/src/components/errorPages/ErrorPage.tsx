"use client";

import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import Text from "@/refresh-components/texts/Text";
import { DOCS_BASE_URL } from "@/lib/constants";
import { SvgAlertCircle } from "@opal/icons";
import { APP_NAME } from "@/lib/appInfo";
import { useTranslation } from "react-i18next";

export default function Error() {
  const { t } = useTranslation();
  return (
    <ErrorPageLayout>
      <div className="flex flex-row items-center gap-2">
        <Text as="p" headingH2>
          {t("errors.errorPages.generalTitle")}
        </Text>
        <SvgAlertCircle className="w-[1.5rem] h-[1.5rem] stroke-text-04" />
      </div>

      <Text as="p" text03>
        {t("errors.errorPages.generalBody1", { appName: APP_NAME })}
      </Text>

      <Text as="p" text03>
        {t("errors.errorPages.generalBody2Admin")}{" "}
        <a
          className="text-action-link-05"
          href={`${DOCS_BASE_URL}?utm_source=app&utm_medium=error_page&utm_campaign=config_error`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("errors.errorPages.documentation")}
        </a>{" "}
        {t("errors.errorPages.generalBody2User")}
      </Text>

      <Text as="p" text03>
        {t("errors.errorPages.generalBody3Prefix")}{" "}
        <a
          className="text-action-link-05"
          href="https://discord.gg/4NA5SbzrWb"
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("errors.errorPages.discordCommunity")}
        </a>{" "}
        {t("errors.errorPages.generalBody3Suffix")}
      </Text>
    </ErrorPageLayout>
  );
}
