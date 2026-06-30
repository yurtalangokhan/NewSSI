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
import Link from "next/link";
import type { Route } from "next";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";

interface LoginPageProps {
  authUrl: string | null;
  spAuthUrl?: string | null;
  authTypeMetadata: AuthTypeMetadata | null;
  nextUrl: string | null;
  oidcError?: string | null;
  hidePageRedirect?: boolean;
  verified?: boolean;
  isFirstUser?: boolean;
  externalKeycloakLogin?: boolean;
}

export default function LoginPage({
  authUrl,
  spAuthUrl,
  authTypeMetadata,
  nextUrl,
  oidcError,
  hidePageRedirect: _hidePageRedirect,
  verified,
  isFirstUser,
  externalKeycloakLogin = false,
}: LoginPageProps) {
  useSendAuthRequiredMessage();
  const { t } = useTranslation();

  useEffect(() => {
    window.sessionStorage.removeItem("logout_in_progress");
  }, []);

  // Honor any existing nextUrl; only default to new team flow for first users with no nextUrl
  const effectiveNextUrl =
    nextUrl ?? (isFirstUser ? "/app?new_team=true" : null);
  const externalLoginHref = (
    effectiveNextUrl
      ? `/auth/ee/login?next=${encodeURIComponent(effectiveNextUrl)}`
      : "/auth/ee/login"
  ) as Route;

  return (
    <div className="flex flex-col w-full justify-center gap-0">
      {verified && (
        <Message
          success
          close={false}
          text={t("auth.emailVerifiedMessage")}
          className="w-full mb-4"
        />
      )}
      {oidcError && (
        <Message error close={false} text={oidcError} className="w-full mb-3" />
      )}
      {authUrl &&
        authTypeMetadata &&
        authTypeMetadata.authType !== AuthType.CLOUD &&
        // basic/oidc auth is handled below w/ the EmailPasswordForm
        authTypeMetadata.authType !== AuthType.BASIC &&
        authTypeMetadata.authType !== AuthType.OIDC && (
          <div className="flex flex-col w-full gap-3">
            <LoginText />
            <SignInButton
              authorizeUrl={authUrl}
              authType={authTypeMetadata?.authType}
            />
          </div>
        )}

      {authTypeMetadata?.authType === AuthType.CLOUD && (
        <div className="w-full justify-center flex flex-col gap-4">
          <LoginText />
          {authUrl && authTypeMetadata && (
            <>
              <SignInButton
                authorizeUrl={authUrl}
                authType={authTypeMetadata?.authType}
              />
              <div className="flex flex-row items-center w-full gap-2">
                <div className="flex-1 border-t border-border" />
                <Text as="p" text03 mainUiMuted>
                  {t("auth.orDivider")}
                </Text>
                <div className="flex-1 border-t border-border" />
              </div>
            </>
          )}
          <EmailPasswordForm shouldVerify={true} nextUrl={effectiveNextUrl} />
          {NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED && (
            <Button href="/auth/forgot-password" className="w-full">
              {t("auth.resetPasswordLink")}
            </Button>
          )}
          <div className="flex items-center justify-center gap-2 pt-2">
            <Text as="p" text03 mainUiMuted>
              {t("auth.noAccount", { defaultValue: "Hesabınız mı yok?" })}
            </Text>
            <Link href="/auth/signup" className="text-link font-medium">
              {t("auth.signupLink", { defaultValue: "Kaydol" })}
            </Link>
          </div>
        </div>
      )}

      {authTypeMetadata?.authType === AuthType.BASIC && (
        <div className="flex flex-col w-full gap-4">
          <LoginText />

          {authTypeMetadata?.oauthEnabled && authUrl && (
            <>
              <SignInButton
                authorizeUrl={authUrl}
                authType={AuthType.GOOGLE_OAUTH}
              />
              <div className="flex flex-row items-center w-full gap-2">
                <div className="flex-1 border-t border-border" />
                <Text as="p" text03 mainUiMuted>
                  {t("auth.orDivider")}
                </Text>
                <div className="flex-1 border-t border-border" />
              </div>
            </>
          )}

          <EmailPasswordForm nextUrl={effectiveNextUrl} />
          <div className="flex items-center justify-center gap-2 pt-2">
            <Text as="p" text03 mainUiMuted>
              {t("auth.noAccount", { defaultValue: "Hesabınız mı yok?" })}
            </Text>
            <Link href="/auth/signup" className="text-link font-medium">
              {t("auth.signupLink", { defaultValue: "Kaydol" })}
            </Link>
          </div>
        </div>
      )}

      {authTypeMetadata?.authType === AuthType.OIDC &&
        externalKeycloakLogin && (
          <div className="flex flex-col w-full gap-4">
            <LoginText />
            {(authUrl || spAuthUrl) && (
              <>
                <div className="flex flex-col w-full gap-2">
                  {authUrl && (
                    <Button href={authUrl} className="w-full">
                      {t("auth.externalSsoLink", {
                        defaultValue: "External SSO",
                      })}
                    </Button>
                  )}
                  {spAuthUrl && (
                    <Button href={spAuthUrl} secondary className="w-full">
                      {t("auth.spSsoLink", {
                        defaultValue: "SP Keycloak SSO",
                      })}
                    </Button>
                  )}
                </div>
                <div className="flex flex-row items-center w-full gap-2">
                  <div className="flex-1 border-t border-border" />
                  <Text as="p" text03 mainUiMuted>
                    {t("auth.orDivider")}
                  </Text>
                  <div className="flex-1 border-t border-border" />
                </div>
              </>
            )}
            <EmailPasswordForm
              nextUrl={effectiveNextUrl}
              loginProvider="external"
            />
          </div>
        )}

      {authTypeMetadata?.authType === AuthType.OIDC &&
        !externalKeycloakLogin && (
          <div className="flex flex-col w-full gap-4">
            <LoginText />

            {authUrl && (
              <>
                <SignInButton authorizeUrl={authUrl} authType={AuthType.OIDC} />
              </>
            )}

            <EmailPasswordForm nextUrl={effectiveNextUrl} />

            {authTypeMetadata?.externalKeycloak && (
              <div className="flex items-center justify-center gap-2 pt-1">
                <Text as="p" text03 mainUiMuted>
                  {t("auth.externalSsoPrompt", {
                    defaultValue: "Use external identity provider?",
                  })}
                </Text>
                <Link
                  href={externalLoginHref}
                  className="text-link font-medium"
                >
                  {t("auth.externalSsoLink", {
                    defaultValue: "External SSO",
                  })}
                </Link>
              </div>
            )}
          </div>
        )}
    </div>
  );
}
