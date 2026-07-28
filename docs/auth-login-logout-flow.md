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

Unauthenticated `/api/auth/me` requests may return 401 before login. That is
normal. After cookies are set, `/api/auth/me` should return 200.

## External Keycloak Login

The `/auth/ee/login` page supports two SP-backed paths:

- SSO button: browser-based SP OIDC authorize request with
  `kc_idp_hint=<external alias>`.
- Form login: server-side brokered password login through
  `POST /api/auth/external/login`.

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
   app cookies. Oversized `id_token` values are not written as cookies because
   large upstream identity claims can make the web proxy reject the login
   response.

Because this is a browser-submitted password form, the password appears in the
browser's own Network request payload. That is expected for any password login
flow. Do not log the payload in frontend, proxy, gateway, or backend logs, and
do not run this flow over plain HTTP outside local development. The SSO button
avoids sending the password to the web app because credentials are entered on
the IdP origin instead.

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
- If refresh returns 401, the app session is expired and the browser is sent to
  the login page selected by `/api/auth/type`.
- If no refresh token is available, the browser is sent to the 401 error page.

Seeing 401 for `/api/auth/refresh` or `/api/auth/me` before login is expected.
It is only a bug if successful login does not turn those requests into 200.

## Logout

Web `/auth/logout`:

1. Calls user-service `/api/auth/logout`.
2. Clears app cookies: `access_token`, `refresh_token`, `id_token`,
   `fastapiusersauth`, and `session`.
3. For OIDC, redirects to Keycloak front-channel logout when possible so the
   browser SSO cookie on the Keycloak origin is also cleared. `id_token_hint` is
   used only when the optional `id_token` cookie exists.

If the SP Keycloak SSO cookie remains alive, pressing the SSO login button may
log in again without asking for credentials. That is normal OIDC behavior and
means Keycloak still has a browser session.

## Useful Checks

Check login mode:

```sh
curl http://localhost:8000/api/auth/type
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
