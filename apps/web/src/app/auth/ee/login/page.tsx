import { User } from "@/lib/types";
import {
  AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { redirect } from "next/navigation";
import type { Route } from "next";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import LoginPage from "@/app/auth/login/LoginPage";
import { buildLoginPath } from "@/lib/auth/loginRoute";

export interface PageProps {
  searchParams?: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function Page(props: PageProps) {
  const searchParams = await props.searchParams;
  const nextUrl: string | null = Array.isArray(searchParams?.next)
    ? searchParams?.next[0] ?? null
    : searchParams?.next ?? null;
  const oidcError: string | null = Array.isArray(searchParams?.oidcError)
    ? searchParams?.oidcError[0] ?? null
    : searchParams?.oidcError ?? null;

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

  return (
    <div className="flex flex-col">
      <AuthFlowContainer>
        <LoginPage
          authUrl={null}
          authTypeMetadata={authTypeMetadata}
          nextUrl={nextUrl}
          oidcError={oidcError}
          hidePageRedirect={true}
          externalKeycloakLogin={true}
        />
      </AuthFlowContainer>
    </div>
  );
}
