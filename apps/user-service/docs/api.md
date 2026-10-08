# User Service API

**Service:** Auth, users, roles, permissions, settings, API keys, user memories, and per-user connector configurations.
**Base URL:** the configured Gateway URL followed by `/user-service`.
**Canonical API prefix:** `/api/v1`
**Auth:** JWT Bearer token (header or `access_token` cookie), except `/api/v1/health` and selected `/api/v1/auth/*` endpoints which are public.

This is the human-maintained endpoint contract for user-service. Prefer
generated OpenAPI output only when you need schema-level detail or client
generation.

Gateway owns browser authentication at `/auth/api/v1/*` and the compatible
`/user-service/api/v1/auth/*` login paths. User-service retains `/auth/me`,
user administration, organization management, and resource assignment APIs.

## Standard JSON response

All 139 application JSON route registrations, including internal and auth routes,
return the service-local `ResponseModel[T]`. CSV export remains a streamed file;
Health and readiness retain their native payloads and HTTP 200/503;
Prometheus `/metrics` remains text. Payload examples elsewhere in this document
show the contents of `data` unless they explicitly include the envelope.

```json
{
  "statusCode": 200,
  "message": null,
  "data": {"id": "example-id"},
  "error": null
}
```

The actual HTTP status matches `statusCode`. Existing creation statuses remain
201. Memory and organization deletion now return HTTP 200 with `data: null`
instead of 204. Existing payload fields and response DTO filtering remain
inside `data`; authentication cookies and OIDC browser redirects keep their
transport behavior.

Shared `ApplicationError` instances propagate from service through controller
to route. The route renders a central error_contract locale key for the
request language and returns the same model. Failed requests carry
`data: null` and `error: {code, message}`. Operational endpoints are excluded. Auth dependencies, request validation, unmatched
routes, unexpected errors, and idempotency failures use this contract too.
Error-defined authentication and retry headers remain available.

Browser domain APIs unwrap `data`; existing Response-based domain mutation
interfaces use a user-service-specific payload adapter. Shared browser/server
HTTP transports keep their raw Response interface. Internal agent, RAG, and
tools clients validate HTTP/body status agreement before extracting data and
preserve upstream error status, code, and localized message. Authorization
helpers retain their existing fallback or failure behavior.

## Organization resource workspace

The organization page requests catalogs and assignments from user-service.
It does not compose agent-service and RAG-service responses itself.

`GET /api/v1/permissions/organizations/{org_id}/targets/{target_type}/`
`{target_id}/resources/{resource_type}/workspace` returns:

```json
{
  "resources": [{"id": "42", "name": "Research", "description": null}],
  "permissions": [],
  "count": 0
}
```

`target_type` is `organization` or `user`; `resource_type` is `agent` or
`rag_collection`. The service checks organization scope and target membership
before fetching the caller-visible catalog through `GATEWAY_URL`. It forwards
the caller's bearer token, without replacing it with privileged credentials.
Upstream access denials return `401` or `403`; unavailable or invalid catalogs
return `503`, rather than an empty successful response. `count` counts direct
permission assignments. Existing scoped PUT requests keep their payload and
response contract; the frontend preserves the catalog when saving assignments.

Internal service-to-service calls use `X-Internal-Service-Token` header.
Compatibility aliases may remain during migration. New integrations must use
the canonical `/api/v1` paths documented here.

---

## Idempotency

Mutating user-service endpoints use the shared idempotency model. Reusing a key
with a different request fingerprint or principal returns
`409 idempotency_key_reused`.

`domain_required` routes reject missing `Idempotency-Key` with
`400 idempotency_key_required`. This category includes user invite, password
reset and set-password operations, permission sync, external IdP sync, full auth user sync, and API key creation because those
operations can create one-time secrets or call external identity systems.

`required_replay` routes include register, user create, role create, coarse-role
create, memory create, and prompt shortcut create. They require keys by default
(`IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=true`). Login, external login, logout, and
refresh are excluded from idempotency.

---

## Health

| Method | Path                   | Auth   | Description                                                            |
| ------ | ---------------------- | ------ | ---------------------------------------------------------------------- |
| GET    | `/api/v1/health`       | Public | Simple health check `{"status": "healthy", "service": "user-service"}` |
| GET    | `/api/v1/health/ready` | Public | Readiness check with DB ping                                           |

---

## Authentication

**Prefix:** `/api/v1/auth`

Authentication supports three modes: OIDC (Keycloak browser redirect), Direct Access Grant (username/password), and external Keycloak broker (federated IdP).

| Method | Path                          | Auth          | Description                                                                          |
| ------ | ----------------------------- | ------------- | ------------------------------------------------------------------------------------ |
| GET    | `/api/v1/auth/type`           | Public        | Returns auth type (`oidc` or `basic`) and Keycloak config status                     |
| POST   | `/api/v1/auth/login`          | Public        | Login with username/password (Keycloak Direct Access Grant). Sets cookies.           |
| POST   | `/api/v1/auth/external/login` | Public        | Login via external Keycloak identity provider broker                                 |
| POST   | `/api/v1/auth/logout`         | Public        | Logout — clears cookies, triggers Keycloak backchannel logout                        |
| POST   | `/api/v1/auth/refresh`        | Public        | Refresh tokens using `refresh_token` cookie                                          |
| GET    | `/api/v1/auth/oidc/authorize` | Public        | Get Keycloak OIDC authorization URL (query: `redirect_uri`, `kc_idp_hint`, `prompt`) |
| GET    | `/api/v1/auth/oidc/callback`  | Public        | Handle OIDC callback — exchanges code for tokens, upserts user                       |
| GET    | `/api/v1/auth/me`             | Gateway       | Get current user's full profile with preferences                                     |
| POST   | `/api/v1/auth/sync-users`     | `user:manage` | Sync all users and roles from Keycloak to local database                             |
| POST   | `/api/v1/auth/register`       | Public        | Register new user (currently raises ValueError — managed by Keycloak)                |

**Cookie-based auth:** Tokens stored in `access_token`, `refresh_token`, `id_token` HTTP-only cookies with `SameSite=Lax`.

**Authentication chain:** Gateway introspects the Keycloak token and applies the route policy, then forwards a user ID with a shared proof header. User-service checks that proof and resolves the profile; it does not validate user tokens.

External Keycloak login uses the identity-provider alias configured in the SP
Keycloak realm. `EXTERNAL_KEYCLOAK=true` controls whether the external login
page is selected. External issuer and client settings are not required for the
login request itself; they are required only when user-service provisions or
updates the external IdP configuration.

User role assignments are Keycloak realm-role mappings. A user's `role` field
is the display name of the primary role, which is stored in the
`agentic.primary_role` user attribute. Every role-assignment endpoint takes
Keycloak realm-role IDs, not role names. New users receive the `enduser` role
unless the create request names another role by `role_id`. A user without any
realm role displays as `enduser`, but that display role grants no access.

---

## Users

**Prefix:** `/api/v1/users`

| Method | Path                                       | Permission    | Description                                                                                  |
| ------ | ------------------------------------------ | ------------- | -------------------------------------------------------------------------------------------- |
| GET    | `/api/v1/users/me`                         | JWT           | Get own profile with preferences and personalization                                         |
| GET    | `/api/v1/users/me/permissions`             | JWT           | Get own resolved permissions                                                                 |
| GET    | `/api/v1/users/me/roles`                   | JWT           | Get own assigned roles                                                                       |
| PATCH  | `/api/v1/users/me`                         | JWT           | Update own profile                                                                           |
| POST   | `/api/v1/users/me/password`                | JWT           | Change own password (raises ValueError — managed by Keycloak)                                |
| GET    | `/api/v1/users/`                           | `user:list`   | List users with pagination and filters (skip, limit, query, role, roles, is_active, invited) |
| POST   | `/api/v1/users/`                           | `user:create` | Create a Keycloak user (body: optional initial `role_id`, default `enduser`)                  |
| GET    | `/api/v1/users/invited`                    | `user:list`   | List pending invited users                                                                   |
| GET    | `/api/v1/users/role-distribution`          | `user:list`   | Primary-role counts from a background-refreshed snapshot (see below)                         |
| GET    | `/api/v1/users/download/csv`               | `user:list`   | Download users as CSV                                                                        |
| POST   | `/api/v1/users/invite`                     | `user:create` | Invite users by email (bulk)                                                                 |
| POST   | `/api/v1/users/{target_id}/role`           | `user:update` | Replace all of the user's realm roles with one role (body: `role_id`)                        |
| GET    | `/api/v1/users/{target_id}/roles`          | `user:read`   | List roles assigned to the user                                                              |
| POST   | `/api/v1/users/{target_id}/roles`          | `user:update` | Add roles by Keycloak ID (body: `role_ids`, optional `primary_role_id` from `role_ids`)      |
| DELETE | `/api/v1/users/{target_id}/roles/{role_id}` | `user:update` | Remove one assigned role; removing the final role is rejected                                |
| POST   | `/api/v1/users/{target_id}/roles/{role_id}/primary` | `user:update` | Mark an assigned role as the primary role                                             |
| POST   | `/api/v1/users/{target_id}/reset-password` | `user:update` | Reset password (raises ValueError)                                                           |
| PATCH  | `/api/v1/users/{target_id}/active`         | `user:update` | Activate/deactivate user                                                                     |
| POST   | `/api/v1/users/{target_id}/password`       | `user:update` | Set user password (raises ValueError)                                                        |
| GET    | `/api/v1/users/{target_id}`                | `user:read`   | Get user by ID                                                                               |
| PATCH  | `/api/v1/users/{target_id}`                | `user:update` | Update user profile                                                                          |
| DELETE | `/api/v1/users/{target_id}`                | `user:delete` | Delete user (local + Keycloak)                                                               |

`user:impersonate` is a system permission for impersonation flows. It is
resolved through the same composite role and feature-bundle chain as other
permissions.

**Response shape example (`GET /api/v1/users/`):**

```json
{
  "items": [
    {
      "id": "...",
      "email": "...",
      "username": "...",
      "first_name": "...",
      "last_name": "...",
      "role": "...",
      "is_active": true
    }
  ],
  "total_items": 42,
  "total": 42,
  "skip": 0,
  "limit": 10
}
```

### Role distribution

`GET /api/v1/users/role-distribution` never computes on the request path.
Counting primary roles walks the whole Keycloak directory, which takes minutes
on a large realm, so the endpoint answers immediately from a snapshot. One
background task refreshes the snapshot once it is older than five minutes.

| `status` | Meaning |
|---|---|
| `ready` | `distribution` holds the last snapshot, possibly while a refresh runs |
| `pending` | The first snapshot is being computed; poll again |
| `unavailable` | The last computation failed and no snapshot exists; it retries after 30 seconds |

The response is `{"status", "distribution": [{"role", "count"}], "computed_at"}`.
A failed refresh keeps serving the last good snapshot. Users without a realm
role are counted under `enduser`, the role the user list displays for them.

---

## Users — Internal endpoints

**Prefix:** `/api/v1/internal/users`

Used by other services (agent-service, rag-service) for service-to-service user lookups.
The batch endpoint accepts 1 to 100 distinct UUID values in the
`user_ids` array and returns public snapshots for matching users only.

| Method | Path                                                  | Auth           | Description                                                     |
| ------ | ----------------------------------------------------- | -------------- | --------------------------------------------------------------- |
| POST   | `/api/v1/internal/users/upsert-from-keycloak`         | JWT / Internal | Create/update user from Keycloak OIDC profile                   |
| POST   | `/api/v1/internal/users/batch`                        | JWT / Internal | Get matching public user snapshots for up to 100 distinct UUIDs |
| GET    | `/api/v1/internal/users/by-keycloak-id/{keycloak_id}` | JWT / Internal | Get user by Keycloak subject ID                                 |
| PATCH  | `/api/v1/internal/users/{target_id}`                  | JWT / Internal | Update user profile                                             |
| GET    | `/api/v1/internal/users/{target_id}/permissions`      | JWT / Internal | Get user's permissions                                          |
| GET    | `/api/v1/internal/users/{target_id}/effective-permissions` | JWT / Internal | Get user's resolved effective permissions                  |
| GET    | `/api/v1/internal/users/{target_id}/roles`            | JWT / Internal | Get user's assigned roles                                       |
| POST   | `/api/v1/internal/users/authorize`                    | JWT / Internal | Check if user has a specific permission                         |

---

## User Settings

**Prefix:** `/api/v1/users/me/settings`

The five public settings routes and five internal settings routes return the
service-local `ResponseModel[dict[str, Any]]`. Success uses HTTP 200 and
`{statusCode: 200, message: null, data: <existing payload>, error: null}`.
Settings defaults and shortcut payload fields stay the same inside `data`.
Shortcut deletion also returns HTTP 200; its existing confirmation is in
`data.message`.

Controller and service failures propagate as shared `ApplicationError` types.
The route sets the HTTP status and returns the same model with `data: null`,
`statusCode` matching HTTP, and `error: {code, message}`. Missing shortcuts use
`settings.shortcut_not_found` (404); missing target users use `user.not_found`
(404). Central error_contract locale keys render the message in the request
language. Existing permission and internal target-access checks still apply.
Auth dependencies, request validation, and unexpected failures raised before
or outside this route catch use the same service-local response model.

Browser preferences APIs check `statusCode` and unwrap `data`. The input-prompt
BFF projects `data.prompt_shortcuts` to an array inside the same model; the
pinned-assistant BFF projects `data.pinned_assistants`. Backend failures are
forwarded without replacing them with an empty success. The agent-service
internal settings client unwraps the model before merging settings defaults
and preserves upstream error status, code, and localized message.

| Method | Path                                                       | Permission        | Description            |
| ------ | ---------------------------------------------------------- | ----------------- | ---------------------- |
| GET    | `/api/v1/users/me/settings/`                               | `settings:read`   | Get own settings       |
| PATCH  | `/api/v1/users/me/settings/`                               | `settings:update` | Update own settings    |
| POST   | `/api/v1/users/me/settings/prompt-shortcuts`               | `settings:update` | Create prompt shortcut |
| PATCH  | `/api/v1/users/me/settings/prompt-shortcuts/{shortcut_id}` | `settings:update` | Update prompt shortcut |
| DELETE | `/api/v1/users/me/settings/prompt-shortcuts/{shortcut_id}` | `settings:update` | Delete prompt shortcut |

### Settings — Internal

**Prefix:** `/api/v1/internal/users`

| Method | Path                                                                         | Auth           | Description                  |
| ------ | ---------------------------------------------------------------------------- | -------------- | ---------------------------- |
| GET    | `/api/v1/internal/users/{target_id}/settings`                                | JWT / Internal | Get any user's settings      |
| PATCH  | `/api/v1/internal/users/{target_id}/settings`                                | JWT / Internal | Update any user's settings   |
| POST   | `/api/v1/internal/users/{target_id}/settings/prompt-shortcuts`               | JWT / Internal | Create shortcut for any user |
| PATCH  | `/api/v1/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}` | JWT / Internal | Update shortcut for any user |
| DELETE | `/api/v1/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}` | JWT / Internal | Delete shortcut for any user |

---

## User Memories

**Prefix:** `/api/v1/users/me/memories`

User memories store facts about the user for agent recall (long-term memory).

The internal RAG memory-index client reads `ResponseModel` acknowledgements:
HTTP 200, `statusCode: 200`, `data: null`, and `error: null`. It forwards the
request language and preserves typed error codes and localized messages on
failure. Background index synchronization retains its existing failure policy.

| Method | Path                                    | Permission      | Description                                              |
| ------ | --------------------------------------- | --------------- | -------------------------------------------------------- |
| GET    | `/api/v1/users/me/memories/`            | `memory:read`   | List memories (query: `page`, `page_size`)               |
| POST   | `/api/v1/users/me/memories/`            | `memory:create` | Create memory (body: `{"content": "..."}`) — returns 201 |
| GET    | `/api/v1/users/me/memories/{memory_id}` | `memory:read`   | Get memory by ID                                         |
| PATCH  | `/api/v1/users/me/memories/{memory_id}` | `memory:update` | Update memory content                                    |
| DELETE | `/api/v1/users/me/memories/{memory_id}` | `memory:delete` | Delete memory — returns 204                              |
| DELETE | `/api/v1/users/me/memories/`            | `memory:delete` | Delete all memories — returns `{"deleted": count}`       |

### Memories — Internal

**Prefix:** `/api/v1/internal/users/{target_id}/memories`

| Method | Path                                                      | Auth           | Description                                                    |
| ------ | --------------------------------------------------------- | -------------- | -------------------------------------------------------------- |
| GET    | `/api/v1/internal/users/{target_id}/memories`             | JWT / Internal | List any user's memories                                       |
| GET    | `/api/v1/internal/users/{target_id}/memories/recall`      | JWT / Internal | Get memories for agent recall (content-only strings)           |
| POST   | `/api/v1/internal/users/{target_id}/memories`             | JWT / Internal | Create memory for any user                                     |
| POST   | `/api/v1/internal/users/{target_id}/memories/bulk`        | JWT / Internal | Bulk add facts (body: `{"contents": [...], "source?": "..."}`) |
| GET    | `/api/v1/internal/users/{target_id}/memories/{memory_id}` | JWT / Internal | Get specific memory                                            |
| PATCH  | `/api/v1/internal/users/{target_id}/memories/{memory_id}` | JWT / Internal | Update memory                                                  |
| DELETE | `/api/v1/internal/users/{target_id}/memories/{memory_id}` | JWT / Internal | Delete memory — 204                                            |
| DELETE | `/api/v1/internal/users/{target_id}/memories`             | JWT / Internal | Delete all memories for user                                   |

---

## Connector Configurations — Internal

**Prefix:** `/api/v1/internal/users/{user_id}/connector-configs`

Connector configurations (source credentials used by agent-service syncs) are
stored per user. The whole configuration document is one Fernet token under
`CONNECTOR_CONFIG_ENCRYPTION_KEY`. Every route requires
`X-Internal-Service-Token`; a gateway user identity is refused with 403,
including the owner's. Responses use the standard envelope above. Only the
single-item GET returns the decrypted `config` inside `data`; all other
responses carry metadata (`id`, `user_id`, `connector_name`, `name`,
`created_at`, `updated_at`). An unreadable ciphertext (wrong or rotated key)
is reported as 409.

| Method | Path                                                              | Auth     | Description                                                          |
| ------ | ----------------------------------------------------------------- | -------- | -------------------------------------------------------------------- |
| GET    | `/api/v1/internal/users/{user_id}/connector-configs`              | Internal | List the user's configurations (metadata only)                       |
| POST   | `/api/v1/internal/users/{user_id}/connector-configs`              | Internal | Create (body: `{"connector_name", "name", "config"}`) — returns 201  |
| GET    | `/api/v1/internal/users/{user_id}/connector-configs/{config_id}`  | Internal | Metadata plus decrypted `config`; 404 when not owned by `user_id`    |
| PUT    | `/api/v1/internal/users/{user_id}/connector-configs/{config_id}`  | Internal | Update `name` and/or replace `config`                                |
| DELETE | `/api/v1/internal/users/{user_id}/connector-configs/{config_id}`  | Internal | Delete — returns 200 with `data: null`; 404 when not owned           |

---

## API Keys

**Prefix:** `/api/v1/users/me/api-keys`

API keys are SHA-256 hashed and Fernet encrypted. The raw key is returned only once on creation.
API key records do not carry user roles, feature bundles, or permission scopes.
Creating, listing, and deleting keys are authorized by the caller's resolved
permissions through `api_key:create`, `api_key:read`, and `api_key:delete`.

| Method | Path                                 | Permission       | Description                                                   |
| ------ | ------------------------------------ | ---------------- | ------------------------------------------------------------- |
| POST   | `/api/v1/users/me/api-keys/`         | `api_key:create` | Create API key (query: `name`). Returns `full_key` only once. |
| GET    | `/api/v1/users/me/api-keys/`         | `api_key:read`   | List own API keys                                             |
| DELETE | `/api/v1/users/me/api-keys/{key_id}` | `api_key:delete` | Revoke/delete API key                                         |

---

## Coarse Roles

**Prefix:** `/api/v1/coarse-roles`

Coarse roles are feature bundles. They group fine-grained permissions under a
compact Keycloak client role, so JWTs carry a small role list instead of the
full permission catalog. The UI presents these bundles by product feature, not
by backend service name.

The catalog includes client roles created directly in Keycloak even when they
have no attributes; they appear with zero permissions and can be assigned to
composite roles or deleted. Keycloak's internal `uma_protection` role is omitted.

A bundle's identity is its Keycloak client-role `id`, which Keycloak generates
and never changes. A bundle name is unique only within its `service_client`, so
every path addresses the bundle by ID. A name or a realm-role ID returns `404`.
Create and update take JSON bodies, and create returns `201`.
List, create, get, and update responses include `is_builtin`. The value is
`true` only for roles marked `agentic.builtin=true` in Keycloak. An absent
attribute or `agentic.builtin=false` returns `false`. App-created bundles omit
the attribute. Guarded identity reconciliation writes `true` when its snapshot
explicitly identifies a built-in role.
Deleting a built-in bundle returns `400`; deleting a custom bundle removes
its Keycloak client role.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/coarse-roles/` | `permission:list` | List feature bundles (query: `service_client`) |
| POST | `/api/v1/coarse-roles/` | `role:manage` | Create feature bundle (body: `name`, `service_client`, `description?`, `permissions?`); `409` if the name exists on that client |
| GET | `/api/v1/coarse-roles/{role_id}` | `permission:list` | Get feature bundle |
| PATCH | `/api/v1/coarse-roles/{role_id}` | `role:manage` | Update the description (body: `description`) |
| DELETE | `/api/v1/coarse-roles/{role_id}` | `role:manage` | Delete a custom feature bundle; `400` for built-in bundles |
| GET | `/api/v1/coarse-roles/{role_id}/permissions` | `permission:list` | Get permissions on feature bundle |
| PUT | `/api/v1/coarse-roles/{role_id}/permissions` | `role:manage` | Set permissions on feature bundle (body: `permissions`) |
| GET | `/api/v1/coarse-roles/aggregated/` | `permission:list` | Union of the expanded permissions of feature bundles (query: `ids` CSV of Keycloak IDs) |
| GET | `/api/v1/coarse-roles/service-clients/list` | `permission:list` | List all service clients |

---

## Composite Roles

**Prefix:** `/api/v1/roles`

Composite roles are user-facing roles. Each one is a Keycloak realm role that
bundles feature bundles as Keycloak composites. Keycloak owns the role and its
grants: `agentic.permissions` holds direct grants and `agentic.builtin` marks
built-in roles. Missing and `false` values mean custom; app-created custom
roles omit the attribute. Changing a role's grants or bundles
invalidates the sessions and the permission resolver cache entries of the users
who hold it.

A composite role's identity is its Keycloak realm-role `id`, which Keycloak
generates and never changes. Every path addresses the role by ID, and the ID is
shown on the admin role page. There is no separate ID attribute, because a copy
would be a second, editable source of truth. A name, a client-role ID, or a
reserved Keycloak role (`offline_access`, `uma_authorization`,
`default-roles-*`) returns `404`. `role_ids` always holds feature-bundle
Keycloak IDs. The list response has a single `roles` key. Create and update take
JSON bodies, and create returns `201`.

Composite roles must not rely on hardcoded role-name semantics. Runtime access
comes from the effective permission set, which Keycloak expands from all
assigned roles and their composites. The `system-admin` role always resolves to
`["*"]`.

The catalog contains exactly three built-in user-facing composite roles:
`system-admin`, `enterprise-admin`, and `enduser`. Startup bootstrap creates or
updates the configured bootstrap admin user and assigns it `system-admin` in
Keycloak.

Use `PUT /api/v1/roles/{role_id}/role-ids` as the primary management path. New
admin flows must not assign direct permissions to composite roles.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/roles/` | `role:list` | List composite roles (`{"roles": [...]}`) |
| POST | `/api/v1/roles/` | `role:manage` | Create composite role (body: `name`, `description?`, `permissions?`, `role_ids?`); `409` if the name exists |
| GET | `/api/v1/roles/{role_id}` | `role:read` | Get composite role |
| PATCH | `/api/v1/roles/{role_id}` | `role:manage` | Update composite role (body: `description?`, `permissions?`, `role_ids?`) |
| DELETE | `/api/v1/roles/{role_id}` | `role:manage` | Delete composite role (blocked if built-in or users assigned) |
| GET | `/api/v1/roles/{role_id}/permissions` | `role:read` | Get effective permissions (direct grants plus feature bundles) |
| PUT | `/api/v1/roles/{role_id}/permissions` | `role:manage` | Set direct permissions (body: `permissions`) |
| GET | `/api/v1/roles/{role_id}/role-ids` | `role:read` | Get feature-bundle IDs and names |
| PUT | `/api/v1/roles/{role_id}/role-ids` | `role:manage` | Set feature bundles by Keycloak ID (body: `role_ids`); returns `effective_permissions` |

---

## Permissions

**Prefix:** `/api/v1/permissions`

Permissions are discovered from distinct `agentic.permissions` attributes on
Keycloak service client roles. A permission appears in this list when at least
one feature bundle grants it. The response retains the same metadata fields;
the user-service manifest supplies its own labels, while other permissions use
labels derived from their names. The sync endpoint reports the discovered
permissions without writing Keycloak roles.
Each catalog entry includes its owning logical `service` and the configured
Keycloak `service_client` ID. Unknown service ownership yields a null client ID.
The admin feature-bundle editor keeps other clients' permissions visible but
disables their checkboxes; saving preserves any existing cross-client grants.

| Method | Path                                    | Permission          | Description                                 |
| ------ | --------------------------------------- | ------------------- | ------------------------------------------- |
| GET    | `/api/v1/permissions/`                  | `permission:list`   | List permissions (query: `service` filter)  |
| GET    | `/api/v1/permissions/coverage`          | `permission:read`   | Get feature → entity → action coverage      |
| GET    | `/api/v1/permissions/entities`          | `permission:list`   | List all unique permission entities         |
| GET    | `/api/v1/permissions/services`          | `permission:list`   | List services with permission counts        |
| POST   | `/api/v1/permissions/sync`              | `permission:manage` | Report discovered permissions from service client roles |
| GET    | `/api/v1/permissions/{permission_name}` | `permission:read`   | Get permission by name                      |

---

## Organizations and scoped resource access

Organizations form one enterprise tree. Only one root organization may exist.
System and enterprise administrators can manage the full tree. Other actors
need the relevant `org:*` action permission, a Unit Manager assignment in
`user_roles`, and active organization membership. Each highest assigned unit becomes a visible tree root. Disjoint
assignments produce multiple roots; ancestors and unrelated units are excluded
from tree, search, details, membership, and statistics responses.
Returned scope roots have `parent_id: null`, a relative path and level, and
`is_scope_root: true`. Managers cannot move, delete, or deactivate those roots,
create global roots, or move descendants outside their assigned scope.

`GET /api/v1/organizations/search?q=...&max_results=100` requires `org:read`.
Every whitespace-separated search word must occur in the organization's name,
code, or description, regardless of word order. For example, `load test 00092`
matches `Load Test Unit 00092`. Matching is case-insensitive; `%` and `_` are
literal characters. Search applies the actor's organization scope before the
result limit and returns `{results: [...], query: "..."}`.

`GET /api/v1/organizations/scope` requires `org:read` and returns
`{global_access: boolean, root_ids: UUID[]}`. Root IDs are empty for global
administrators. Navigation uses `org:view`; tree and member reads use
`org:read`. Create and mutation operations keep their corresponding action
gates. Scope violations return HTTP 403.

Organization role selectors use the same platform assignments as the Users page.
`user_roles` is authoritative; `users.role` remains a derived mirror. The unchanged
`role_in_org` response field projects the primary assigned platform role (or the
first assigned role if none is primary); it is empty only if no role is assigned.
The same value is included in `user.role`. Migration 0046 removes the obsolete database column
`user_organizations.role_in_org`; the API alias does not store a second role.

Adding a member or changing the selector writes through User Service's single-role
setter, synchronizing `user_roles`, the mirror, Keycloak and permission caches.
It replaces the user's platform assignments, so the role applies across all their
units. A Unit Manager manages their active assigned units and their descendants.
Removing membership removes that unit scope, not the user's platform role.

| Method | Path                                                                                                     | Auth                           | Description                                                  |
| ------ | -------------------------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------ |
| GET    | `/api/v1/organizations`                                                                                  | JWT                            | List organizations                                           |
| POST   | `/api/v1/organizations`                                                                                  | org:create and unit scope    | Create an organization; rejects a second root                |
| GET    | `/api/v1/organizations/tree`                                                                             | JWT                            | Return the organization tree                                 |
| GET    | `/api/v1/organizations/members`                                                                          | `org:read`                     | Return active direct memberships grouped by organization ID  |
| GET    | `/api/v1/organizations/{org_id}/management-capability`                                                   | JWT                            | Report whether the actor can manage the unit                 |
| POST   | `/api/v1/organizations/{org_id}/move`                                                                    | `org:move` and organization scope | Reparent a unit; delegates cannot move their assigned root or move outside their subtree |
| GET    | `/api/v1/organizations/{org_id}/users`                                                                   | JWT                            | List organization members                                    |
| POST   | `/api/v1/organizations/{org_id}/users`                                                                   | Manager scope                  | Add an organization member                                   |
| PATCH  | `/api/v1/organizations/{org_id}/users/{user_id}`                                                         | Manager scope                  | Change membership state or organization role                 |
| DELETE | `/api/v1/organizations/{org_id}/users/{user_id}`                                                         | Manager scope                  | Remove an organization member                                |
| GET    | `/api/v1/permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}` | Manager scope                  | List direct scoped resource permissions                      |
| PUT    | `/api/v1/permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}` | Manager scope                  | Replace direct scoped resource permissions                   |

`target_type` is `organization` or `user`; `resource_type` is `agent` or
`rag_collection`. An organization target must match `org_id`. A user target must be
an active member of that organization. The scoped `PUT` synchronizes the
submitted direct grants atomically: omitted grants are revoked, existing grants
are updated, and new grants are created. Reads require `org:read`; replacement
requires `org:manage-resources`. Delegated actors must hold both the old and new
permission levels before changing or removing a grant. They cannot assign
administrator membership roles or elevate their own unit-manager scope.
Parent-unit permissions are not inherited by child units or their users.

`GET /api/v1/organizations/{org_id}/assignable-users?query=&limit=20`
requires authentication. Authoritative global administrators are allowed;
delegated actors need `org:manage-users` and management scope for the destination.
The response is `{ "users": [...], "total": 0 }`; each user contains `id`, `email`,
`first_name`, `last_name`, and `username`. The server searches email, name, and
username across all eligible users before applying `limit` (1–100, default 20).
`total` counts all matching eligible users, including matches beyond the result
limit. Search text is case-insensitive and accepts at most 200 characters.

System and Enterprise administrators can search all users. Delegated unit
managers can search only users with active memberships in active organizations
within their permitted subtrees. Active destination members are excluded.
Assignment enforces the same candidate scope, including bulk requests; an
eligible user's inactive destination membership is reactivated.

Unit managers can select only End User and cannot change their own role or
replace a target's privileged/custom role. Global administrators may select
other catalog roles; System Admin and Enterprise Admin remain excluded from
this selector. Existing admin roles are still displayed. End User and Unit
Manager spelling variants resolve to canonical platform catalog names.
Migration 0045 backfills only users without any assignment from their valid
existing platform role; it never promotes legacy membership manager values.

Membership deletion and orphan cleanup are atomic. Removing a user from one
unit preserves their direct agent, collection, and other user-target resource
permissions while they retain another active organization membership. Removing
their final active membership deletes all `resource_permissions` rows targeted
to that user. Permissions targeted to organizations or other users and the
permission audit history are not deleted.

The bulk organization-members response contains direct active memberships
only. It includes each member's public identity fields and groups memberships
by their owning organization ID. It doesn't include inherited or descendant
unit memberships.

Scope violations return `403`, invalid targets return `400`, and missing
organizations return `404`. A concurrent attempt to create a second root
returns `409`.

### Chat resource decisions

`POST /api/v1/permissions/check` and
`GET /api/v1/permissions/users/{identity}/accessible-resources` resolve local
user UUIDs or Keycloak subjects. They combine direct user grants with grants on
active organization memberships. The strongest effective level wins; a weaker
direct grant does not mask a stronger organization grant. Parent-unit resource
grants remain independent from child units.

Accessible-resource requests accept `required_permission` (`execute`, `read`,
`write`, `admin`, or `owner`) to filter by effective level. Agent selection and
execution require `execute`; collection discovery and retrieval require `read`.
Resource services retain their intentional public, owner, and administrator
access paths. Failed permission lookups do not grant access. General permission
and audit listings are restricted to global administrators; organization-scoped
reads remain available inside the actor's permitted subtree.

### Automatic visual layout

The diagram computes positions locally from the visible scoped hierarchy. It
starts with two levels and reveals children on expansion. Vertical and horizontal
resets change the current view orientation and fit the compact tree; they do not
fetch the complete hierarchy or save coordinates. The orientation starts vertical
when the designer opens.

There is no layout endpoint or `organization_layouts` table after migration 0048.
Drag-and-drop changes the parent through `POST /organizations/{org_id}/move`,
which requires `org:move` and validates both source and destination scope. Assigned
scope roots cannot be moved. Descendant parent links are preserved. View controls
remain available without move permission.

---

## System Settings

**Prefix:** `/api/v1/system-settings`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/system-settings/keycloak` | `system.settings:read` | Get full Keycloak configuration |
| PATCH | `/api/v1/system-settings/keycloak` | `system.settings:update` | Update Keycloak configuration (fields encrypted before storage) |
| PATCH | `/api/v1/system-settings/keycloak/realm-session` | `system.settings:update` | Update Keycloak realm session token lifespans |
| POST | `/api/v1/system-settings/keycloak/external-idp/sync` | `system.settings:update` | Sync external identity provider to Keycloak |

The realm-session update accepts `access_token_lifespan`,
`sso_session_idle_timeout`, `sso_session_max_lifespan`, and
`client_session_max_lifespan` in seconds. Set
`client_session_max_lifespan` to `0` to inherit the realm's SSO session maximum;
otherwise, use a value from `60` through `2592000`.
| Method | Path                                                 | Auth         | Description                                                     |
| ------ | ---------------------------------------------------- | ------------ | --------------------------------------------------------------- |
| GET    | `/api/v1/system-settings/keycloak`                   | System Admin | Get full Keycloak configuration                                 |
| PATCH  | `/api/v1/system-settings/keycloak`                   | System Admin | Update Keycloak configuration (fields encrypted before storage) |
| PATCH  | `/api/v1/system-settings/keycloak/realm-session`     | System Admin | Update Keycloak realm session token lifespans                   |
| POST   | `/api/v1/system-settings/keycloak/external-idp/sync` | System Admin | Sync external identity provider to Keycloak                     |

---

## Auth dependency hierarchy

```
require_auth_or_internal_service_token
  └─ get_current_user_id (token from header or cookie)
      └─ returns "internal-service" for X-Internal-Service-Token

require_auth                → get_current_user_id → raises 401 if None
require_permission("perm")  → require_auth → checks Keycloak-resolved
                              permissions of the user's effective roles
```

**Permission detection:** Endpoints authorize requests by checking the resolved
permission set. The resolver reads the user's effective Keycloak realm roles,
lets Keycloak expand their composites into feature bundles, and returns the
union of their `agentic.permissions`. `system-admin` resolves to `["*"]`.

---

## Keycloak architecture

Keycloak is the source of truth for users, roles, permissions, and
assignments. PostgreSQL holds only application data such as settings, API keys,
memories, and audit logs.

- **User CRUD** → creates, updates, and deletes Keycloak users
- **Role management** → Keycloak realm-role mappings. The primary role is the `agentic.primary_role` attribute, and feature bundles are Keycloak client roles.
- **Password management** → Delegated entirely to Keycloak (service raises `ValueError`)
- **Token validation** → Gateway introspection and route authorization; user-service trusts only Gateway's verified identity headers
- **Login** → Keycloak Direct Access Grant or OIDC redirect
- **External IdP** → Keycloak identity provider broker with federated identity bridging

Single-role user profile updates replace authorization role assignments and invalidate the effective-access cache. Keycloak primary-role refreshes synchronize the primary assignment while preserving explicit secondary roles. Organization moves still require configured `org:move` permission.

Organization membership identities expose `user.role` and the compatibility field `role_in_org` from `user_roles`; neither uses the legacy membership role column.

Organization membership flags: `is_primary` identifies the user's main organization for primary-organization retrieval and membership ordering; it grants no extra authority. `is_active` controls whether that membership participates in member lists/counts, access eligibility, and Unit Manager scope. It is separate from the account-level `users.is_active`.

Organization moves preserve every descendant parent link. The moved node changes parent; descendant paths and levels are rebuilt from the subtree's parent links. Paths contain ancestors only (root path `/`). Migration 0047 repairs older seed/move path and level inconsistencies without changing organization parent links.
