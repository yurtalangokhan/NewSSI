import type { AuthTypeMetadata } from "@/lib/userSS";

type LoginRouteMetadata = Pick<AuthTypeMetadata, "externalKeycloak"> & {
  external_keycloak?: boolean;
};

export const getLoginPath = (
  authTypeMetadata: LoginRouteMetadata | null | undefined
) =>
  authTypeMetadata?.externalKeycloak || authTypeMetadata?.external_keycloak
    ? "/auth/ee/login"
    : "/auth/login";

export const buildLoginPath = (
  authTypeMetadata: LoginRouteMetadata | null | undefined,
  nextUrl?: string | null
) => {
  const loginPath = getLoginPath(authTypeMetadata);

  if (!nextUrl) {
    return loginPath;
  }

  return `${loginPath}?next=${encodeURIComponent(nextUrl)}`;
};
