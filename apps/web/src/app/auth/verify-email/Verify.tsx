"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Text from "@/components/ui/text";
import { getErrorMsg } from "@/lib/fetchUtils";
import { RequestNewVerificationEmail } from "../waiting-on-verification/RequestNewVerificationEmail";
import { User } from "@/lib/types";
import Logo from "@/refresh-components/Logo";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import { useTranslation } from "react-i18next";
import { idempotentFetch } from "@/lib/api/idempotency";

export interface VerifyProps {
  user: User | null;
}

export default function Verify({ user }: VerifyProps) {
  const searchParams = useSearchParams();
  const { t } = useTranslation();

  const [error, setError] = useState("");

  const verify = useCallback(async () => {
    const token = searchParams?.get("token");
    const firstUser =
      searchParams?.get("first_user") === "true" && NEXT_PUBLIC_CLOUD_ENABLED;
    if (!token) {
      setError(t("auth.verifyEmail.missingToken"));
      return;
    }

    const response = await idempotentFetch("/api/auth/verify", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token }),
    });

    if (response.ok) {
      const loginUrl = firstUser
        ? "/auth/login?verified=true&first_user=true"
        : "/auth/login?verified=true";
      window.location.href = loginUrl;
    } else {
      let errorDetail = "unknown error";
      try {
        errorDetail = (await getErrorMsg(response)) ?? errorDetail;
      } catch (e) {
        console.error("Failed to parse verification error response:", e);
      }
      setError(t("auth.verifyEmail.failed", { detail: errorDetail }));
    }
  }, [searchParams, t]);

  useEffect(() => {
    verify();
  }, [verify]);

  return (
    <main>
      <div className="min-h-screen flex flex-col items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <Logo folded size={64} className="mx-auto w-fit animate-pulse" />
        {!error ? (
          <Text className="mt-2">{t("auth.verifyEmail.verifying")}</Text>
        ) : (
          <div>
            <Text className="mt-2">{error}</Text>

            {user && (
              <div className="text-center">
                <RequestNewVerificationEmail email={user.email}>
                  <Text className="mt-2 text-link">
                    {t("auth.verifyEmail.getNewEmail")}
                  </Text>
                </RequestNewVerificationEmail>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
