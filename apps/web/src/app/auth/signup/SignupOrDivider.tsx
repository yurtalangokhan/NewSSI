"use client";

import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

export default function SignupOrDivider() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center w-full my-4">
      <div className="flex-grow border-t border-border-01" />
      <Text as="p" mainUiMuted text03 className="mx-2">
        {t("auth.orDivider")}
      </Text>
      <div className="flex-grow border-t border-border-01" />
    </div>
  );
}
