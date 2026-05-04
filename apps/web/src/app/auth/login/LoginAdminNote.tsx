"use client";

import { useTranslation } from "react-i18next";

export function LoginAdminNote() {
  const { t } = useTranslation();
  return <>{t("authPages.loginAdminNote")}</>;
}
