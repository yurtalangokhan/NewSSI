"use client";

import React from "react";
import { useTranslation } from "react-i18next";

interface ErrorPageLayoutProps {
  children: React.ReactNode;
}

export default function ErrorPageLayout({ children }: ErrorPageLayoutProps) {
  const { t } = useTranslation("common", { keyPrefix: "common" });
  return (
    <div className="flex flex-col items-center justify-center w-full h-screen gap-4">
      <img
        src="/logo.turksat.svg"
        alt={t("turksatLogoAlt")}
        className="h-auto w-[120px] dark:hidden"
        draggable={false}
      />
      <img
        src="/logo.turksat.white.svg"
        alt={t("turksatLogoAlt")}
        className="h-auto w-[120px] hidden dark:block"
        draggable={false}
      />
      <div className="max-w-[40rem] w-full border bg-background-neutral-00 shadow-02 rounded-16 p-6 flex flex-col gap-4">
        {children}
      </div>
    </div>
  );
}
