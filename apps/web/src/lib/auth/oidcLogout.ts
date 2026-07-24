import { AuthType } from "@/lib/constants";

interface BuildOidcLogoutUrlArgs {
  authType: AuthType;
  issuer?: string | null;
  clientId: string;
  postLogoutRedirectUri: string;
  idTokenHint?: string | null;
}

export function buildOidcLogoutUrl({
  authType,
  issuer,
  clientId,
  postLogoutRedirectUri,
  idTokenHint,
}: BuildOidcLogoutUrlArgs): URL | null {
  if (authType !== AuthType.OIDC || !issuer) {
    return null;
  }

  const logoutUrl = new URL(
    `${issuer.replace(/\/$/, "")}/protocol/openid-connect/logout`
  );
  logoutUrl.searchParams.set("client_id", clientId);
  logoutUrl.searchParams.set("post_logout_redirect_uri", postLogoutRedirectUri);
  if (idTokenHint) {
    logoutUrl.searchParams.set("id_token_hint", idTokenHint);
  }
  return logoutUrl;
}
