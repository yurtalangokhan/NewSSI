"use client";

import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";

export function JoinHeading() {
  const { t } = useTranslation();
  return (
    <Text as="h2" className="text-center text-xl text-strong font-bold">
      {t("auth.reauthenticateHeading")}
    </Text>
  );
}

export function OrDivider() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center w-full my-4">
      <div className="flex-grow border-t border-background-300"></div>
      <span className="px-4 text-text-500">{t("auth.orDivider")}</span>
      <div className="flex-grow border-t border-background-300"></div>
    </div>
  );
}
