"use client";

import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import { REGISTRATION_URL } from "@/lib/constants";
import Button from "@/refresh-components/buttons/Button";
import Link from "next/link";
import { SvgImport } from "@opal/icons";
import { useTranslation } from "react-i18next";

export default function Page() {
  const { t } = useTranslation();

  return (
    <AuthFlowContainer>
      <div className="flex flex-col space-y-6">
        <h2 className="text-2xl font-bold text-text-900 text-center">
          {t("authPages.createAccount.notFoundTitle")}
        </h2>
        <p className="text-text-700 max-w-md text-center">
          {t("authPages.createAccount.description")}
        </p>
        <ul className="list-disc text-left text-text-600 w-full pl-6 mx-auto">
          <li>{t("authPages.createAccount.inviteOption")}</li>
          <li>{t("authPages.createAccount.createTeamOption")}</li>
        </ul>
        <div className="flex justify-center">
          <Button
            href={`${REGISTRATION_URL}/register`}
            className="w-full"
            leftIcon={SvgImport}
          >
            {t("authPages.createAccount.createOrgButton")}
          </Button>
        </div>
        <p className="text-sm text-text-500 text-center">
          {t("authPages.createAccount.differentEmailText")}{" "}
          <Link
            href="/auth/login"
            className="text-action-link-05 hover:underline"
          >
            {t("authPages.createAccount.signInLink")}
          </Link>
        </p>
      </div>
    </AuthFlowContainer>
  );
}
