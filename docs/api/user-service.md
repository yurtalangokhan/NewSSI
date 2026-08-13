# User Service API

**Service:** Auth, users, roles, permissions, settings, API keys, and user memories.
**Base URL:** `http://kong:8000/user-service` (via Kong gateway) or `http://user-service:8090` (direct)
**Canonical API prefix:** `/api/v1`
**Auth:** JWT Bearer token (header or `access_token` cookie), except `/api/v1/health` and selected `/api/v1/auth/*` endpoints which are public.

Internal service-to-service calls use `X-Internal-Service-Token` header.
Compatibility aliases may remain during migration. New integrations must use
the canonical `/api/v1` paths documented here.

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
| GET    | `/api/v1/auth/me`             | JWT           | Get current user's full profile with preferences                                     |
| POST   | `/api/v1/auth/sync-users`     | `user:manage` | Sync all users and roles from Keycloak to local database                             |
| POST   | `/api/v1/auth/register`       | Public        | Register new user (currently raises ValueError — managed by Keycloak)                |

**Cookie-based auth:** Tokens stored in `access_token`, `refresh_token`, `id_token` HTTP-only cookies with `SameSite=Lax`.

**Token validation chain:** Local HS256 JWT → Keycloak JWKS → Keycloak userinfo → External Keycloak userinfo.

External Keycloak login uses the identity-provider alias configured in the SP
Keycloak realm. `EXTERNAL_KEYCLOAK=true` controls whether the external login
page is selected. External issuer and client settings are not required for the
login request itself; they are required only when user-service provisions or
updates the external IdP configuration.

User records store exactly one composite role in `role`. New users receive the
default `enduser` composite role when no existing local assignment exists.
Login, refresh, and external Keycloak sync flows preserve an existing local
composite role instead of deriving one from token client roles. The legacy
`is_superuser` flag is not part of the authorization model.

---

## Users

**Prefix:** `/api/v1/users`

| Method | Path                                       | Permission    | Description                                                                                  |
| ------ | ------------------------------------------ | ------------- | -------------------------------------------------------------------------------------------- |
| GET    | `/api/v1/users/me`                         | JWT           | Get own profile with preferences and personalization                                         |
| GET    | `/api/v1/users/me/permissions`             | JWT           | Get own resolved permissions                                                                 |
| PATCH  | `/api/v1/users/me`                         | JWT           | Update own profile                                                                           |
| POST   | `/api/v1/users/me/password`                | JWT           | Change own password (raises ValueError — managed by Keycloak)                                |
| GET    | `/api/v1/users/`                           | `user:list`   | List users with pagination and filters (skip, limit, query, role, roles, is_active, invited) |
| POST   | `/api/v1/users/`                           | `user:create` | Create user (local + Keycloak)                                                               |
| GET    | `/api/v1/users/invited`                    | `user:list`   | List pending invited users                                                                   |
| GET    | `/api/v1/users/download/csv`               | `user:list`   | Download users as CSV                                                                        |
| POST   | `/api/v1/users/invite`                     | `user:create` | Invite users by email (bulk)                                                                 |
| POST   | `/api/v1/users/{target_id}/role`           | `user:update` | Set user role                                                                                |
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
| POST   | `/api/v1/internal/users/authorize`                    | JWT / Internal | Check if user has a specific permission                         |

---

## User Settings

**Prefix:** `/api/v1/users/me/settings`

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
compact Keycloak client role so JWTs carry a small role list instead of the
full permission catalog. The UI presents these bundles by product feature, not
by backend service name.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/coarse-roles/` | `permission:list` | List feature bundles (query: `service_client`) |
| POST | `/api/v1/coarse-roles/` | `role:manage` | Create feature bundle (query: `name`, `service_client`, `description?`) |
| GET | `/api/v1/coarse-roles/{role_name}` | `permission:list` | Get feature bundle by name |
| PATCH | `/api/v1/coarse-roles/{role_name}` | `role:manage` | Update feature bundle |
| DELETE | `/api/v1/coarse-roles/{role_name}` | `role:manage` | Delete feature bundle |
| GET | `/api/v1/coarse-roles/{role_name}/permissions` | `permission:list` | Get permissions on feature bundle |
| PUT | `/api/v1/coarse-roles/{role_name}/permissions` | `role:manage` | Set permissions on feature bundle |
| GET | `/api/v1/coarse-roles/aggregated/` | `permission:list` | Aggregate permissions from multiple feature bundle names (query: `names` CSV) |
| GET | `/api/v1/coarse-roles/service-clients/list` | `permission:list` | List all service clients |

---

## Composite Roles

**Prefix:** `/api/v1/roles`

Composite roles are user-facing role records. They aggregate feature bundles
through `role_ids`. Changes to composite roles invalidate user sessions.

Composite roles must not rely on hardcoded role-name semantics. Runtime access
comes from the effective permission set resolved from the assigned feature
bundles.

The catalog contains exactly three built-in user-facing composite roles:
`system-admin`, `enterprise-admin`, and `enduser`. The startup bootstrap
selects the default administrator role by `is_admin=true`, syncs the role
catalog to Keycloak, creates or updates the configured bootstrap admin user,
and assigns that selected role in Keycloak and the local user record. The
bootstrap does not use a role-name mapping environment variable.

Use `PUT /api/v1/roles/{role_name}/role-ids` as the primary management path.
The direct permissions endpoint remains for legacy compatibility and migration
workflows; new admin flows must not assign direct permissions to composite
roles.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/roles/` | `role:list` | List all composite roles |
| POST | `/api/v1/roles/` | `role:manage` | Create composite role (body: `name`, `description?`, `role_ids?`) |
| GET | `/api/v1/roles/{role_name}` | `role:read` | Get composite role by name |
| PATCH | `/api/v1/roles/{role_name}` | `role:manage` | Update composite role |
| DELETE | `/api/v1/roles/{role_name}` | `role:manage` | Delete composite role (blocked if built-in or users assigned) |
| GET | `/api/v1/roles/{role_name}/permissions` | `role:read` | Get effective permissions (legacy direct permissions + feature bundles) |
| PUT | `/api/v1/roles/{role_name}/permissions` | `role:manage` | Set legacy direct permissions |
| GET | `/api/v1/roles/{role_name}/role-ids` | `role:read` | Get feature bundle references |
| PUT | `/api/v1/roles/{role_name}/role-ids` | `role:manage` | Set feature bundle references |
| POST | `/api/v1/roles/sync-keycloak` | `role:manage` | Sync all roles to Keycloak |

---

## Permissions

**Prefix:** `/api/v1/permissions`

Permissions are synced from service manifests (user-service, agent-service, rag-service, tools-service).

| Method | Path                                    | Permission          | Description                                 |
| ------ | --------------------------------------- | ------------------- | ------------------------------------------- |
| GET    | `/api/v1/permissions/`                  | `permission:list`   | List permissions (query: `service` filter)  |
| GET    | `/api/v1/permissions/entities`          | `permission:list`   | List all unique permission entities         |
| GET    | `/api/v1/permissions/services`          | `permission:list`   | List services with permission counts        |
| POST   | `/api/v1/permissions/sync`              | `permission:manage` | Sync permissions from all service manifests |
| GET    | `/api/v1/permissions/{permission_name}` | `permission:read`   | Get permission by name                      |

---

## Organizations and scoped resource access

Organizations form one enterprise tree. Only one root organization may exist.
Enterprise administrators can manage the full tree. A member with the
`unit_manager` organization role can manage membership, organization roles,
and direct resource access for their own unit and its descendants.

Organization membership role selectors reuse the authoritative composite-role
catalog returned by `GET /api/v1/roles` and add the organization-specific
`unit_manager` value. Membership writes accept a current composite-role name or
`unit_manager`. The UI displays that special value as **Birim Yöneticisi**.
Other values, including `member` and `viewer`, must exist in the catalog.
Unknown role names return `400`. A catalog role stored in
`role_in_org` does not grant enterprise-wide administrator scope—only an
actor's platform role or an explicit `unit_manager` membership affects
organization-management scope.

| Method | Path                                                                                                     | Auth                           | Description                                                  |
| ------ | -------------------------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------ |
| GET    | `/api/v1/organizations`                                                                                  | JWT                            | List organizations                                           |
| POST   | `/api/v1/organizations`                                                                                  | Enterprise admin               | Create an organization; rejects a second root                |
| GET    | `/api/v1/organizations/tree`                                                                             | JWT                            | Return the organization tree                                 |
| GET    | `/api/v1/organizations/layout`                                                                           | `org:read`                     | Return shared canvas positions and writable organization IDs |
| PUT    | `/api/v1/organizations/layout`                                                                           | `org:update` and manager scope | Atomically upsert shared canvas positions                    |
| GET    | `/api/v1/organizations/members`                                                                          | `org:read`                     | Return active direct memberships grouped by organization ID  |
| GET    | `/api/v1/organizations/{org_id}/management-capability`                                                   | JWT                            | Report whether the actor can manage the unit                 |
| POST   | `/api/v1/organizations/{org_id}/move`                                                                    | Manager scope                  | Move below another unit; moving to the root is rejected      |
| GET    | `/api/v1/organizations/{org_id}/users`                                                                   | JWT                            | List organization members                                    |
| POST   | `/api/v1/organizations/{org_id}/users`                                                                   | Manager scope                  | Add an organization member                                   |
| PATCH  | `/api/v1/organizations/{org_id}/users/{user_id}`                                                         | Manager scope                  | Change membership state or organization role                 |
| DELETE | `/api/v1/organizations/{org_id}/users/{user_id}`                                                         | Manager scope                  | Remove an organization member                                |
| GET    | `/api/v1/permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}` | Manager scope                  | List direct scoped resource permissions                      |
| PUT    | `/api/v1/permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}` | Manager scope                  | Replace direct scoped resource permissions                   |

`target_type` is `organization` or `user`; `resource_type` is `agent` or
`collection`. An organization target must match `org_id`. A user target must be
an active member of that organization. The scoped `PUT` synchronizes the
submitted direct grants atomically: omitted grants are revoked, existing grants
are updated, and new grants are created. Parent-unit permissions are not
inherited by child units or their users.

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

### Shared visual layout

The organization designer stores one shared set of canvas coordinates. Layout
records are separate from organization metadata and use the organization ID as
their key. Deleting an organization cascades to its layout record.

`GET /api/v1/organizations/layout` returns all saved positions in ascending
organization-ID order:

```json
{
  "positions": [
    {
      "organization_id": "8a60ec52-f318-45cf-9880-361b725b8d51",
      "x": 120.5,
      "y": 240
    }
  ],
  "writable_organization_ids": ["8a60ec52-f318-45cf-9880-361b725b8d51"]
}
```

The writable-ID list reflects the actor's organization-management scope and
lets the client disable dragging without making one capability request per
node. Read-only nodes remain selectable.

`PUT /api/v1/organizations/layout` accepts up to 500 unique positions. Each
coordinate must be a finite number from `-1000000` through `1000000`:

```json
{
  "positions": [
    {
      "organization_id": "8a60ec52-f318-45cf-9880-361b725b8d51",
      "x": 160,
      "y": 280
    }
  ]
}
```

The service validates every organization and the actor's scope before writing
the batch. A mixed-authority batch fails without saving any positions. An
empty batch succeeds with `{"positions": [], "count": 0}`. Duplicate IDs
return `400`, scope violations return `403`, missing or concurrently deleted
organizations return `404`, persistence conflicts return `409`, and schema or
coordinate violations return `422`.

---

## System Settings

**Prefix:** `/api/v1/system-settings`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/system-settings/keycloak` | `system.settings:read` | Get full Keycloak configuration |
| PATCH | `/api/v1/system-settings/keycloak` | `system.settings:update` | Update Keycloak configuration (fields encrypted before storage) |
| PATCH | `/api/v1/system-settings/keycloak/realm-session` | `system.settings:update` | Update Keycloak realm session token lifespans |
| POST | `/api/v1/system-settings/keycloak/external-idp/sync` | `system.settings:update` | Sync external identity provider to Keycloak |
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
require_admin               → require_auth → checks admin-area permissions
require_system_admin        → require_auth → checks system settings permissions
require_permission("perm")  → require_auth → checks DB-resolved permissions
                              through composite roles and feature bundles
```

**Permission detection:** Endpoints authorize requests by checking the resolved
permission set returned by user-service.

---

## Keycloak architecture

Keycloak is the source of truth. The service mirrors user data, roles, and permissions to a local PostgreSQL database.

- **User CRUD** → creates/updates/deletes in both Keycloak and local DB
- **Role management** → Composite roles in DB, synced to Keycloak realm roles + compact feature-bundle client roles
- **Password management** → Delegated entirely to Keycloak (service raises `ValueError`)
- **Token validation** → 4-step fallback chain: local HS256 → JWKS → userinfo → external Keycloak
- **Login** → Keycloak Direct Access Grant or OIDC redirect
- **External IdP** → Keycloak identity provider broker with federated identity bridging
