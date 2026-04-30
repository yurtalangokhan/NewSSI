"use client";

import { useEffect } from "react";
import { toast } from "@/hooks/useToast";
import { useTranslation } from "react-i18next";

export default function AuthErrorDisplay({
  searchParams,
}: {
  searchParams: any;
}) {
  const { t } = useTranslation();
  const error = searchParams?.error;

  useEffect(() => {
    if (error) {
      toast.error(
        error === "Anonymous"
          ? t("authPages.errorDisplay.anonymousAccess")
          : t("authPages.errorDisplay.genericError")
      );
    }
  }, [error, t]);

  return null;
}
