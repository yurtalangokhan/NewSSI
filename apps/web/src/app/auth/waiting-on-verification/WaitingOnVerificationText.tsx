"use client";

import Text from "@/components/ui/text";
import { RequestNewVerificationEmail } from "./RequestNewVerificationEmail";
import { useTranslation } from "react-i18next";

interface WaitingOnVerificationTextProps {
  email: string;
}

export default function WaitingOnVerificationText({
  email,
}: WaitingOnVerificationTextProps) {
  const { t } = useTranslation();

  return (
    <div className="flex">
      <Text className="text-center font-medium text-lg mt-6 w-108">
        {t("auth.waitingOnVerification.greeting", { email: "" })}
        <i>{email}</i>
        {t("auth.waitingOnVerification.notVerifiedYet")}
        <br />
        {t("auth.waitingOnVerification.checkInbox")}
        <br />
        <br />
        {t("auth.waitingOnVerification.dontSeeIt")}{" "}
        <RequestNewVerificationEmail email={email}>
          {t("auth.waitingOnVerification.here")}
        </RequestNewVerificationEmail>{" "}
        {t("auth.waitingOnVerification.requestNewEmail")}
      </Text>
    </div>
  );
}
