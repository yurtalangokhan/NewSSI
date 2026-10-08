// Additional auth paths

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const sessionEndpoints = {
  getCurrentUser: {
    method: "GET",
    browserPath: "/api/me",
    backend: { service: "user", path: "/api/v1/auth/me" },
  },
  createPersonalAccessToken: {
    method: "POST",
    browserPath: "/api/user/pats",
    backend: { service: "user", path: "/api/v1/users/me/api-keys/" },
  },
  listPersonalAccessTokens: {
    method: "GET",
    browserPath: "/api/user/pats",
    backend: { service: "user", path: "/api/v1/users/me/api-keys/" },
  },
  deletePersonalAccessToken: (patId: string | number) =>
    ({
      method: "DELETE",
      browserPath: `/api/user/pats/${patId}`,
      backend: { service: "user", path: `/api/v1/users/me/api-keys/${patId}` },
    }) as const,
  authorizeOidc: {
    method: "GET",
    browserPath: "/api/auth/oidc/authorize",
    backend: { service: "user", path: "/api/v1/auth/oidc/authorize" },
  },
  login: {
    method: "POST",
    browserPath: "/api/auth/login",
    backend: { service: "user", path: "/api/v1/auth/login" },
  },
  getLogin: {
    method: "GET",
    browserPath: "/api/auth/login",
    backend: { service: "user", path: "/api/v1/auth/login" },
  },
  externalLogin: {
    method: "POST",
    browserPath: "/api/auth/external/login",
    backend: { service: "user", path: "/api/v1/auth/external/login" },
  },
  refresh: {
    method: "POST",
    browserPath: "/api/auth/refresh",
    backend: { service: "user", path: "/api/v1/auth/refresh" },
  },
  register: {
    method: "POST",
    browserPath: "/api/auth/register",
    backend: { service: "user", path: "/api/v1/auth/register" },
  },
  authType: {
    method: "GET",
    browserPath: "/api/auth/type",
    backend: { service: "user", path: "/api/v1/auth/type" },
  },
  forgotPassword: { browserPath: "/api/auth/forgot-password" },
  resetPassword: { browserPath: "/api/auth/reset-password" },
  requestVerifyToken: { browserPath: "/api/auth/request-verify-token" },
  verifyEmail: { browserPath: "/api/auth/verify" },
  loginAnonymousTenantUser: (pathValue: string): { browserPath: string } => {
    return {
      browserPath: `/api/tenants/anonymous-user?anonymous_user_path=${pathValue}`,
    };
  },
  impersonateTenantUser: { browserPath: "/api/tenants/impersonate" },
  refreshEnterpriseSession: {
    browserPath: "/api/enterprise-settings/refresh-token",
  },
  oidcCallback: {
    backend: { service: "user", path: "/api/v1/auth/oidc/callback" },
  },
  oauthCallback: {
    backend: { service: "user", path: "/api/v1/auth/oauth/callback" },
  },
  samlCallback: {
    backend: { service: "user", path: "/api/v1/auth/saml/callback" },
  },
  logout: { backend: { service: "user", path: "/api/v1/auth/logout" } },
  samlLogout: {
    backend: { service: "user", path: "/api/v1/auth/saml/logout" },
  },
  samlAuthorize: {
    backend: { service: "agent", path: "/api/v1/auth/saml/authorize" },
  },
  changeAccountPassword: { browserPath: "/api/user-service/users/me/password" },
  oauthAuthorize: { browserPath: "/api/auth/oauth/authorize" },
} as const;
