"use client";

import Link from "next/link";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useEffect, useState } from "react";

export default function AuthFlowContainer({
  children,
  authState,
  footerContent,
}: {
  children: React.ReactNode;
  authState?: "signup" | "login" | "join";
  footerContent?: React.ReactNode;
}) {
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
      <div className="auth-login-bg-glow auth-login-bg-glow-1" aria-hidden="true" />
      <div className="auth-login-bg-glow auth-login-bg-glow-2" aria-hidden="true" />

      {/* Header with Language Switcher */}
      <div className="absolute top-6 right-6 z-20">
        <LanguageSwitcher variant="button" />
      </div>

      <div className="w-full max-w-md flex items-start flex-col bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl p-10 z-10 text-white">
        {/* Logo Section */}
        <div className="flex flex-col items-center w-full mb-10">
          {mounted && (
            <img
              src={logoSrc}
              alt="Turksat Logo"
              className="h-16 w-auto drop-shadow-lg"
              draggable={false}
            />
          )}
        </div>

        <div className="w-full">{children}</div>
      </div>
      {authState === "login" && (
        <div className="text-sm mt-6 text-center w-full text-white/80 mainUiBody mx-auto">
          {footerContent ?? (
            <>
              New to AgenticAI Platform?{" "}
              <Link
                href="/auth/signup"
                className="text-white mainUiAction underline transition-colors duration-200"
              >
                Create an Account
              </Link>
            </>
          )}
        </div>
      )}
      {authState === "signup" && (
        <div className="text-sm mt-6 text-center w-full text-white/80 mainUiBody mx-auto">
          Already have an account?{" "}
          <Link
            href="/auth/login"
            className="text-white mainUiAction underline transition-colors duration-200"
          >
            Sign In
          </Link>
        </div>
      )}
    </div>
  );
}
