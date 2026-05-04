"use client";

import React, { useContext } from "react";
import { SettingsContext } from "@/providers/SettingsProvider";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

export default function LoginText() {
  const settings = useContext(SettingsContext);
  const { t } = useTranslation();
  const appName =
    (settings && settings?.enterpriseSettings?.application_name) ||
    "AgenticAI Platform";
  return (
    <div className="w-full flex flex-col ">
      <Text as="p" headingH2 text05>
        {t("auth.welcomeHeading", { appName })}
      </Text>
      <Text as="p" text03 mainUiMuted>
        {t("auth.tagline")}
      </Text>
    </div>
  );
}
