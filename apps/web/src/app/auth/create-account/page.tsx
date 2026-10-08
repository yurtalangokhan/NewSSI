"use client";

import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import Button from "@/refresh-components/buttons/Button";
import Link from "next/link";
import { SvgImport } from "@opal/icons";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import { useContext } from "react";
import { SettingsContext } from "@/providers/SettingsProvider";

export default function Page() {
  const { t } = useTranslation();
  const settings = useContext(SettingsContext);

  // The registration link used to be built from a server-only service URL
  // variable. In this client component it was never inlined, so the href
  // resolved through the old `|| "http://127.0.0.1:3001"` fallback in every
  // build. `webDomain` is the app's configured public origin and already
  // reaches the client on CombinedSettings.
  const registrationUrl = `${settings?.webDomain ?? ""}/register`;

  return (
    <AuthFlowContainer>
      <div className="flex flex-col space-y-6">
        <Text as="h2" className="text-2xl font-bold text-text-900 text-center">
          {t("authPages.createAccount.notFoundTitle")}
        </Text>
        <Text as="p" className="text-text-700 max-w-md text-center">
          {t("authPages.createAccount.description")}
        </Text>
        <ul className="list-disc text-left text-text-600 w-full pl-6 mx-auto">
          <li>{t("authPages.createAccount.inviteOption")}</li>
          <li>{t("authPages.createAccount.createTeamOption")}</li>
        </ul>
        <div className="flex justify-center">
          <Button
            href={registrationUrl}
            className="w-full"
            leftIcon={SvgImport}
          >
            {t("authPages.createAccount.createOrgButton")}
          </Button>
        </div>
        <Text as="p" className="text-sm text-text-500 text-center">
          {t("authPages.createAccount.differentEmailText")}{" "}
          <Link
            href="/auth/login"
            className="text-action-link-05 hover:underline"
          >
            {t("authPages.createAccount.signInLink")}
          </Link>
        </Text>
      </div>
    </AuthFlowContainer>
  );
}
