import {
  AuthTypeMetadata,
  getAuthUrlSS,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { redirect } from "next/navigation";
import type { Route } from "next";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import LoginPage from "@/app/auth/login/LoginPage";
import { buildLoginPath } from "@/lib/auth/loginRoute";
import type { User } from "@/lib/types";

export interface PageProps {
  searchParams?: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function Page(props: PageProps) {
  const searchParams = await props.searchParams;
  const nextUrl: string | null = Array.isArray(searchParams?.next)
    ? searchParams?.next[0] ?? null
    : searchParams?.next ?? null;
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

  if (!authTypeMetadata?.externalKeycloak) {
    return redirect(buildLoginPath(authTypeMetadata, nextUrl) as Route);
  }

  if (currentUser && currentUser.is_active && !currentUser.is_anonymous_user) {
    if (authTypeMetadata?.requiresVerification && !currentUser.is_verified) {
      return redirect("/auth/waiting-on-verification");
    }

    return redirect("/app");
  }

  const spAuthUrl = await getAuthUrlSS(
    authTypeMetadata.authType,
    nextUrl,
    null,
    { prompt: "login" }
  );

  return (
    <div className="flex flex-col">
      <AuthFlowContainer authState="login">
        <LoginPage
          authUrl={null}
          spAuthUrl={spAuthUrl}
          authTypeMetadata={authTypeMetadata}
          nextUrl={nextUrl}
          hidePageRedirect={true}
          externalKeycloakLogin={true}
        />
      </AuthFlowContainer>
    </div>
  );
}
