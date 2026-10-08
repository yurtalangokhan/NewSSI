"use client";
import { loginAnonymousTenantUser } from "@/lib/api/domains/session/api";

import { redirect } from "next/navigation";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import Skeleton from "@/refresh-components/skeletons/Skeleton";

export default function AnonymousPage({
  anonymousPath,
}: {
  anonymousPath: string;
}) {
  const { t } = useTranslation("common", { keyPrefix: "anonymousPage" });
  const loginAsAnonymousUser = async () => {
    try {
      const response = await loginAnonymousTenantUser(
        encodeURIComponent(anonymousPath)
      );

      if (!response.ok) {
        console.error("Failed to login as anonymous user", response);
        throw new Error("Failed to login as anonymous user");
      }
      // Redirect to the chat page and force a refresh
      window.location.href = "/app";
    } catch (error) {
      console.error("Error logging in as anonymous user:", error);
      redirect("/auth/signup?error=Anonymous");
    }
  };

  useEffect(() => {
    loginAsAnonymousUser();
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background-100">
      <div className="bg-white p-8 rounded-lg shadow-md">
        <Text as="h1" className="text-2xl font-bold mb-4 text-center">
          {t("redirecting")}
        </Text>
        <div className="flex justify-center">
          <Skeleton className="h-12 w-12 rounded-full" />
        </div>
        <Text as="p" className="mt-4 text-text-600 text-center">
          {t("settingUpSession")}
        </Text>
      </div>
    </div>
  );
}
