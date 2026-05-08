import Link from "next/link";

export default function AuthFlowContainer({
  children,
  authState,
  footerContent,
}: {
  children: React.ReactNode;
  authState?: "signup" | "login" | "join";
  footerContent?: React.ReactNode;
}) {
  return (
    <div className="auth-login-shell p-4 flex flex-col items-center justify-center min-h-screen relative overflow-hidden text-white">
      <div className="auth-login-bg-gradient" aria-hidden="true" />
      <div className="auth-login-bg-grid" aria-hidden="true" />
      <div className="auth-login-bg-glow auth-login-bg-glow-1" aria-hidden="true" />
      <div className="auth-login-bg-glow auth-login-bg-glow-2" aria-hidden="true" />

      <div className="w-full max-w-md flex items-start flex-col bg-background-tint-00/90 backdrop-blur-md border border-border rounded-16 shadow-lg shadow-02 p-6 z-10 text-white">
        <div className="h-11 w-11 rounded-12 bg-theme-primary-05 text-white flex items-center justify-center font-semibold text-lg ring-2 ring-white/30">
          AI
        </div>
        <div className="w-full mt-3">{children}</div>
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
            href="/auth/login?autoRedirectToSignup=false"
            className="text-white mainUiAction underline transition-colors duration-200"
          >
            Sign In
          </Link>
        </div>
      )}
    </div>
  );
}
