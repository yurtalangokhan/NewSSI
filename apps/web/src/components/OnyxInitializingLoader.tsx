"use client";

import { useContext } from "react";
import Logo from "@/refresh-components/Logo";
import { SettingsContext } from "@/providers/SettingsProvider";
import { useTranslation } from "react-i18next";

export default function OnyxInitializingLoader() {
  const { t } = useTranslation("admin");
  const settings = useContext(SettingsContext);

  return (
    <div className="mx-auto my-auto animate-pulse">
      <Logo folded size={96} className="mx-auto mb-3" />
      <p className="text-lg text-text font-semibold">
        {t("initializingLoader", {
          applicationName:
            settings?.enterpriseSettings?.application_name ?? "Onyx",
        })}
      </p>
    </div>
  );
}
