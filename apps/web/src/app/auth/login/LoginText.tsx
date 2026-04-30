"use client";

import React, { useContext } from "react";
import { SettingsContext } from "@/providers/SettingsProvider";
import Text from "@/refresh-components/texts/Text";

export default function LoginText() {
  const settings = useContext(SettingsContext);
  const appName =
    (settings && settings?.enterpriseSettings?.application_name) ||
    "AgenticAI Platform";

  return (
    <div className="w-full flex flex-col ">
      <Text as="p" headingH2 text05>
        Welcome to {appName}
      </Text>
      <Text as="p" text03 mainUiMuted>
        Your AI platform for autonomous workflows
      </Text>
    </div>
  );
}
