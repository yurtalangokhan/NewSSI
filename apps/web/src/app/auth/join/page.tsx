import { User } from "@/lib/types";
import {
  getCurrentUserSS,
  getAuthTypeMetadataSS,
  AuthTypeMetadata,
  getAuthUrlSS,
} from "@/lib/userSS";
import { redirect } from "next/navigation";
import type { Route } from "next";
import EmailPasswordForm from "../login/EmailPasswordForm";
import SignInButton from "@/app/auth/login/SignInButton";
import { JoinHeading, OrDivider } from "./JoinAuthUI";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import AuthErrorDisplay from "@/components/auth/AuthErrorDisplay";
import { AuthType } from "@/lib/constants";

const Page = async (props: {
  searchParams?: Promise<{ [key: string]: string | string[] | undefined }>;
}) => {
  const searchParams = await props.searchParams;
  const nextUrl = Array.isArray(searchParams?.next)
    ? searchParams?.next[0]
    : searchParams?.next || null;

  const defaultEmail = Array.isArray(searchParams?.email)
    ? searchParams?.email[0]
    : searchParams?.email || null;

  // catch cases where the backend is completely unreachable here
  // without try / catch, will just raise an exception and the page
  // will not render
  let authTypeMetadata: AuthTypeMetadata | null = null;
  let currentUser: User | null = null;
  try {
    [authTypeMetadata, currentUser] = await Promise.all([
      getAuthTypeMetadataSS(),
      getCurrentUserSS(),
    ]);
  } catch (e) {
    console.log(`Some fetch failed for the login page - ${e}`);
  }

  // if user is already logged in, take them to the main app page
  if (currentUser && currentUser.is_active && !currentUser.is_anonymous_user) {
    if (!authTypeMetadata?.requiresVerification || currentUser.is_verified) {
      return redirect("/app");
    }
    return redirect("/auth/waiting-on-verification");
  }
  const cloud = authTypeMetadata?.authType === AuthType.CLOUD;

  const oidc = authTypeMetadata?.authType === AuthType.OIDC;

  // only enable this page if an interactive auth flow is enabled
  if (authTypeMetadata?.authType !== AuthType.BASIC && !cloud && !oidc) {
    return redirect("/app");
  }

  let authUrl: string | null = null;
  if ((cloud || oidc) && authTypeMetadata) {
    authUrl = await getAuthUrlSS(authTypeMetadata.authType, null);
  }
  if (oidc && authUrl) {
    return redirect(authUrl as Route);
  }
  return (
    <AuthFlowContainer authState="join">
      <AuthErrorDisplay searchParams={searchParams} />

      <>
        <div className="absolute top-10x w-full"></div>
        <div className="flex w-full flex-col justify-center">
          <JoinHeading />

          {cloud && authUrl && (
            <div className="w-full justify-center">
              <SignInButton authorizeUrl={authUrl} authType={AuthType.CLOUD} />
              <OrDivider />
            </div>
          )}

          <EmailPasswordForm
            isSignup
            isJoin
            shouldVerify={authTypeMetadata?.requiresVerification}
            nextUrl={nextUrl}
            defaultEmail={defaultEmail}
          />
        </div>
      </>
    </AuthFlowContainer>
  );
};

export default Page;
