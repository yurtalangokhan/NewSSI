"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { CRAFT_PATH } from "@/app/craft/v1/constants";
import { useTranslation } from "react-i18next";

/**
 * Build Page - Redirects to the new Build V1 page
 *
 * The new Build experience is at /craft/v1
 * This page exists for backwards compatibility.
 */
export default function BuildPage() {
  const { t } = useTranslation("common", { keyPrefix: "app" });
  const router = useRouter();

  useEffect(() => {
    router.replace(CRAFT_PATH);
  }, [router]);

  return (
    <div className="flex items-center justify-center h-screen">
      <div className="animate-pulse text-text-03">{t("redirecting")}</div>
    </div>
  );
}
