"use client";

import { useTranslation } from "react-i18next";

export function JoinHeading() {
  const { t } = useTranslation();
  return (
    <h2 className="text-center text-xl text-strong font-bold">
      {t("auth.reauthenticateHeading")}
    </h2>
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
