import type { AuthTypeMetadata } from "@/lib/userSS";

export const getLoginPath = (
  authTypeMetadata?: AuthTypeMetadata | null | undefined
) =>
  authTypeMetadata?.externalKeycloak
    ? ("/auth/ee/login" as const)
    : ("/auth/login" as const);

export const buildLoginPath = (
  authTypeMetadata: AuthTypeMetadata | null | undefined,
  nextUrl?: string | null
) => {
  const loginPath = getLoginPath(authTypeMetadata);

  if (!nextUrl) {
    return loginPath;
  }

  return `${loginPath}?next=${encodeURIComponent(nextUrl)}`;
};
