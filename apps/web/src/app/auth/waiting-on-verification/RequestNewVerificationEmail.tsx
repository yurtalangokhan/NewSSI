"use client";

import { toast } from "@/hooks/useToast";
import { getErrorMsg } from "@/lib/fetchUtils";
import { requestEmailVerification } from "../lib";
import { useTranslation } from "react-i18next";
import { Spinner } from "@/components/Spinner";
import { useState, JSX } from "react";

export function RequestNewVerificationEmail({
  children,
  email,
}: {
  children: JSX.Element | string;
  email: string;
}) {
  const { t } = useTranslation();
  const [isRequestingVerification, setIsRequestingVerification] =
    useState(false);

  return (
    <button
      className="text-link"
      onClick={async () => {
        setIsRequestingVerification(true);
        const response = await requestEmailVerification(email);
        setIsRequestingVerification(false);

        if (response.ok) {
          toast.success(t("auth.waitingOnVerification.toastVerificationSent"));
        } else {
          const errorDetail = await getErrorMsg(response);
          toast.error(
            t("auth.waitingOnVerification.toastVerificationFailed", {
              error: errorDetail,
            })
          );
        }
      }}
    >
      {isRequestingVerification && <Spinner />}
      {children}
    </button>
  );
}
