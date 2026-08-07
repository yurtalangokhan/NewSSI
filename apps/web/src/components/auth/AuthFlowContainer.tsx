"use client";

import Link from "next/link";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

export default function AuthFlowContainer({
  children,
  authState,
  footerContent,
}: {
  children: React.ReactNode;
  authState?: "signup" | "login" | "join";
  footerContent?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Always use white logo since auth background is always dark blue
  const logoSrc = "/logo.turksat.white.svg";

  return (
    <div className="auth-login-shell p-4 flex flex-col items-center justify-center min-h-screen relative overflow-hidden text-white">
      <div className="auth-login-bg-gradient" aria-hidden="true" />
      <div className="auth-login-bg-grid" aria-hidden="true" />
      <div
        className="auth-login-bg-glow auth-login-bg-glow-1"
        aria-hidden="true"
      />
      <div
        className="auth-login-bg-glow auth-login-bg-glow-2"
        aria-hidden="true"
      />

      {/* Language Switcher in top right corner */}
      <div className="absolute top-4 right-4 z-20">
        <LanguageSwitcher variant="button" />
      </div>

      <div className="relative z-10 w-full max-w-md bg-[#131b2e]/90 border border-slate-700/60 shadow-2xl rounded-2xl p-8 backdrop-blur-xl transition-all">
        {/* Logo Section */}
        <div className="flex justify-center mb-8">
          {mounted && (
            <img
              src={logoSrc}
              alt={t("auth.welcomeHeading", { appName: "Logo" })}
              className="h-16 w-auto drop-shadow-lg"
              draggable={false}
            />
          )}
        </div>

        <div className="w-full">{children}</div>
      </div>
      {authState === "login" && footerContent && (
        <div className="text-sm mt-6 text-center w-full text-white/80 mainUiBody mx-auto">
          {footerContent}
        </div>
      )}
      {authState === "signup" && (
        <div className="text-sm mt-6 text-center w-full text-white/80 mainUiBody mx-auto">
          {t("auth.alreadyHaveAccountPrompt")}{" "}
          <Link
            href="/auth/login"
            className="text-white mainUiAction underline transition-colors duration-200"
          >
            {t("auth.signInButton")}
          </Link>
        </div>
      )}
    </div>
  );
}
