"use client";

import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

interface SignupHeaderProps {
  cloud: boolean;
}

export default function SignupHeader({ cloud }: SignupHeaderProps) {
  const { t } = useTranslation();
  return (
    <div className="w-full">
      <Text as="p" headingH2 text05>
        {cloud ? t("auth.completeSignUp") : t("auth.createAccount")}
      </Text>
      <Text as="p" text03>
        {t("auth.getStarted")}
      </Text>
    </div>
  );
}
