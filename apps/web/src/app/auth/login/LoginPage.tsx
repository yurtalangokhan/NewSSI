"use client";

import { AuthTypeMetadata } from "@/lib/userSS";
import LoginText from "@/app/auth/login/LoginText";
import SignInButton from "@/app/auth/login/SignInButton";
import EmailPasswordForm from "./EmailPasswordForm";
import { AuthType, NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED } from "@/lib/constants";
import { useSendAuthRequiredMessage } from "@/lib/extension/utils";
import Text from "@/refresh-components/texts/Text";
import Button from "@/refresh-components/buttons/Button";
import Message from "@/refresh-components/messages/Message";
import { useTranslation } from "react-i18next";

interface LoginPageProps {
  authUrl: string | null;
  authTypeMetadata: AuthTypeMetadata | null;
  nextUrl: string | null;
  oidcError?: string | null;
  hidePageRedirect?: boolean;
  verified?: boolean;
  isFirstUser?: boolean;
}

export default function LoginPage({
  authUrl,
  authTypeMetadata,
  nextUrl,
  oidcError,
  hidePageRedirect,
  verified,
  isFirstUser,
}: LoginPageProps) {
  useSendAuthRequiredMessage();
  const { t } = useTranslation();

  // Honor any existing nextUrl; only default to new team flow for first users with no nextUrl
  const effectiveNextUrl =
    nextUrl ?? (isFirstUser ? "/app?new_team=true" : null);

  return (
    <div className="flex flex-col w-full justify-center">
      {verified && (
        <Message
          success
          close={false}
          text={t("auth.emailVerifiedMessage")}
          className="w-full mb-4"
        />
      )}
      {oidcError && (
        <Message
          error
          close={false}
          text={oidcError}
          className="w-full mb-4"
        />
      )}
      {authUrl &&
        authTypeMetadata &&
        authTypeMetadata.authType !== AuthType.CLOUD &&
        // basic auth is handled below w/ the EmailPasswordForm
        authTypeMetadata.authType !== AuthType.BASIC && (
          <div className="flex flex-col w-full gap-4">
            <LoginText />
            <SignInButton
              authorizeUrl={authUrl}
              authType={authTypeMetadata?.authType}
            />
          </div>
        )}

      {authTypeMetadata?.authType === AuthType.CLOUD && (
        <div className="w-full justify-center flex flex-col gap-6">
          <LoginText />
          {authUrl && authTypeMetadata && (
            <>
              <SignInButton
                authorizeUrl={authUrl}
                authType={authTypeMetadata?.authType}
              />
              <div className="flex flex-row items-center w-full gap-2">
                <div className="flex-1 border-t border-text-01" />
                <Text as="p" text03 mainUiMuted>
                  {t("auth.orDivider")}
                </Text>
                <div className="flex-1 border-t border-text-01" />
              </div>
            </>
          )}
          <EmailPasswordForm shouldVerify={true} nextUrl={effectiveNextUrl} />
          {NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED && (
            <Button href="/auth/forgot-password">{t("auth.resetPasswordLink")}</Button>
          )}
        </div>
      )}

      {authTypeMetadata?.authType === AuthType.BASIC && (
        <div className="flex flex-col w-full gap-6">
          <LoginText />

          {authTypeMetadata?.oauthEnabled && authUrl && (
            <>
              <SignInButton
                authorizeUrl={authUrl}
                authType={AuthType.GOOGLE_OAUTH}
              />
              <div className="flex flex-row items-center w-full gap-2">
                <div className="flex-1 border-t border-text-01" />
                <Text as="p" text03 mainUiMuted>
                  {t("auth.orDivider")}
                </Text>
                <div className="flex-1 border-t border-text-01" />
              </div>
            </>
          )}

          <EmailPasswordForm nextUrl={effectiveNextUrl} />
        </div>
      )}

      {!hidePageRedirect && (
        <p className="text-center mt-4 text-white/90">
          {t("auth.noAccountPrompt")}{" "}
          <span
            onClick={() => {
              if (typeof window !== "undefined" && window.top) {
                window.top.location.href = "/auth/signup";
              } else {
                window.location.href = "/auth/signup";
              }
            }}
            className="text-white font-medium cursor-pointer underline"
          >
            {t("auth.createAccountLink")}
          </span>
        </p>
      )}
    </div>
  );
}
