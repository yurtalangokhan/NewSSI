"use client";

import React, { useContext } from "react";
import { SettingsContext } from "@/providers/SettingsProvider";
import { useTranslation } from "react-i18next";
import { getAppName } from "@/lib/appInfo";
import Text from "@/refresh-components/texts/Text";

export default function LoginText() {
  const settings = useContext(SettingsContext);
  const { t } = useTranslation();
  const appName = getAppName(settings?.enterpriseSettings?.application_name);
  return (
    <div className="w-full flex flex-col gap-3 mb-2">
      <Text
        as="h2"
        className="text-2xl font-semibold text-white tracking-tight"
      >
        {t("auth.welcomeHeading", { appName })}
      </Text>
      <Text as="p" className="text-sm text-white/70 font-normal">
        {t("auth.tagline")}
      </Text>
    </div>
  );
}
