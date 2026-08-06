# Auth Login and Logout Flow

This document explains the platform authentication paths for developers,
operators, and future agents debugging login issues.

## Components

- Web app: `apps/web`
- User service: `apps/user-service`
- Gateway: Kong on `http://localhost:8000`
- Service-provider Keycloak: the platform realm, usually `agenticai`
- External Keycloak IdP: optional upstream Keycloak connected to SP Keycloak as
  an identity provider alias, usually `external-keycloak`

All external traffic should go through Kong. Local launch configs read
`apps/*/.env`; infrastructure compose reads `configs/.env`.

## Login Page Selection

The web app calls `/api/auth/type`.

- `externalKeycloak: false` selects `/auth/login`.
- `externalKeycloak: true` selects `/auth/ee/login`.

The user-service response is controlled by:

- `KEYCLOAK_ENABLED=true`
- `EXTERNAL_KEYCLOAK=true`
- external IdP settings such as `EXTERNAL_KEYCLOAK_ISSUER_URL`,
  `EXTERNAL_KEYCLOAK_CLIENT_ID`, and `EXTERNAL_KEYCLOAK_CLIENT_SECRET`

If `EXTERNAL_KEYCLOAK=false` is present in `apps/user-service/.env`, it
overrides runtime settings and `/api/auth/type` reports `externalKeycloak:false`.

## Standard OIDC Login

1. Browser opens `/auth/login`.
2. Web calls `/api/auth/oidc/authorize`.
3. user-service ensures the SP Keycloak login client accepts the runtime web
   callback URI.
4. Browser redirects to SP Keycloak.
5. SP Keycloak returns to `/auth/oidc/callback` with an authorization code.
6. Web forwards the callback to user-service.
7. user-service exchanges the code for SP tokens, mirrors the user locally, and
   sets `access_token` and `refresh_token` cookies. `id_token` is only set as an
   optional logout hint when it fits within browser-safe cookie size.

The web authorize and callback route handlers call user-service through Kong's
service-scoped `/user-service/api/v1/auth/...` path. The frontend's
server-side URL helpers normalize older `/api/auth/...` inputs to that
canonical gateway path.

Unauthenticated `/api/auth/me` requests may return 401 before login. That is
normal. After cookies are set, `/api/auth/me` should return 200.

## External Keycloak Login

The `/auth/ee/login` page supports the external Keycloak IdP form and one
explicit SP Keycloak login action:

- Form login: server-side brokered password login through
  `POST /api/auth/external/login`.
- SP Keycloak SSO button: browser-based SP OIDC authorize request with
  `prompt=login`.

The form login flow is:

1. Web posts the supplied username/password to `/api/auth/external/login`.
2. user-service starts an SP Keycloak authorize request with
   `kc_idp_hint=external-keycloak`.
3. user-service ensures the SP login client accepts the callback URI, for
   example `http://localhost:3000/auth/oidc/callback` in local development.
4. SP Keycloak redirects to the external IdP login form.
5. user-service posts the supplied credentials to that external IdP form.
6. Redirects return through SP Keycloak to the web callback with an SP
   authorization code.
7. user-service exchanges the SP code for SP tokens, mirrors the user, and sets
   app cookies. The app `access_token` and `refresh_token` come from SP
   Keycloak. `id_token` values are not written as cookies when they exceed the
   individual cookie size or total auth `Set-Cookie` header budget because large
   upstream identity claims can make the gateway reject the login response.

Because this is a browser-submitted password form, the password appears in the
browser's own Network request payload. That is expected for any password login
flow. Do not log the payload in frontend, proxy, gateway, or backend logs, and
do not run this flow over plain HTTP outside local development. The SSO button
avoids sending the password to the web app because credentials are entered on
the SP Keycloak origin instead. It uses `prompt=login` so returning from an
expired app session doesn't silently reuse an existing SP Keycloak browser SSO
cookie.

If SP Keycloak rejects the callback URI, the response can be a 400 HTML page
from `/protocol/openid-connect/auth`. Add the rejected callback URI to the SP
Keycloak login client's Valid Redirect URIs, or let user-service register it by
starting with admin credentials configured.

If the external IdP rejects its broker redirect URI, add the SP broker endpoint
to the external Keycloak client:

`<SP issuer>/broker/<external alias>/endpoint`

## Refresh and Expiry

When an API call receives 401, the web app attempts `POST /api/auth/refresh`.

- If refresh succeeds, the original request is retried.
- If refresh fails, the app session is expired and the browser is sent through
  `/auth/logout?next=<login-url>`. That route clears app cookies and, for OIDC,
  redirects to Keycloak front-channel logout before returning to the login page
  selected by `/api/auth/type`.
- After a refresh failure, the web app suppresses repeated refresh attempts for
  that browser tab until a login page is mounted. The login page clears that
  marker so the first 401 after the next successful login can refresh normally.

Client-facing Next.js API proxies and page middleware must return or pass
through auth state without calling the refresh endpoint themselves. This keeps
refresh token rotation centralized in the browser-side authenticated fetcher
and prevents server-side request races from consuming the refresh token before
the browser can refresh and retry the original request.

The authenticated fetcher notifies the app shell after a successful refresh.
The app shell then reloads the current user metadata and recalculates its local
expiry timer. If that timer reaches the access-token deadline before another
request triggers refresh, the app shell verifies the session through the
authenticated fetcher. It doesn't show the expired-session state unless that
verification confirms that refresh cannot recover the session. As a result,
authenticated API activity keeps the session active while the refresh token
remains valid.

Seeing 401 for `/api/auth/refresh` or `/api/auth/me` before login is expected.
It is only a bug if successful login does not turn those requests into 200.

Refresh token expiry and the SP Keycloak browser SSO cookie are independent.
Keycloak client session settings can expire the refresh token while the browser
SSO session is still valid. The logout redirect above clears the app cookies
and attempts to clear that browser SSO session so the next SP SSO login requires
credentials again.

## Logout

Web `/auth/logout`:

1. Calls user-service `/api/auth/logout`.
2. Clears app cookies: `access_token`, `refresh_token`, `id_token`,
   `fastapiusersauth`, and `session`.
3. For OIDC, redirects to Keycloak front-channel logout when possible so the
   browser SSO cookie on the Keycloak origin is also cleared. `id_token_hint` is
   used only when the optional `id_token` cookie exists.

If the SP Keycloak SSO cookie remains alive, an authorize request without
`prompt=login` can log in again without asking for credentials. The web login
page uses `prompt=login` for the SP SSO button to avoid that silent reuse.

## Useful Checks

Check login mode:

```sh
curl http://localhost:8000/user-service/api/v1/auth/type
```

Check whether the browser app sees the same mode:

```sh
curl http://localhost:3000/api/auth/type
```

Expected external login mode:

```json
{
  "authType": "oidc",
  "externalKeycloak": true,
  "external_keycloak": true
}
```

When debugging `400 Bad Request` from `/api/auth/external/login`, inspect the
reported URL:

- SP `/protocol/openid-connect/auth`: SP login client redirect URI problem.
- External issuer `/protocol/openid-connect/auth`: external client redirect URI
  or upstream IdP problem.
- Login form after credential post: invalid credentials or an unsupported IdP
  login form.

When the frontend shows an unknown login error, inspect the
`/api/auth/external/login` response body. The form reads `detail`, `error`, and
`message` fields, then falls back to raw text.
