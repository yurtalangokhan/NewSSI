"use client";

import Text from "@/refresh-components/texts/Text";
import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import { APP_NAME } from "@/lib/appInfo";
import { useTranslation } from "react-i18next";

export default function CloudError() {
  const { t } = useTranslation();
  return (
    <ErrorPageLayout>
      <Text as="p" headingH2>
        {t("errors.errorPages.cloudErrorTitle")}
      </Text>

      <Text as="p" text03>
        {t("errors.errorPages.cloudErrorBody1", { appName: APP_NAME })}
      </Text>

      <Text as="p" text03>
        {t("errors.errorPages.cloudErrorBody2")}
      </Text>
    </ErrorPageLayout>
  );
}
