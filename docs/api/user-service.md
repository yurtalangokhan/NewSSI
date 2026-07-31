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

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | Public | Simple health check `{"status": "healthy", "service": "user-service"}` |
| GET | `/api/v1/health/ready` | Public | Readiness check with DB ping |

---

## Authentication

**Prefix:** `/api/v1/auth`

Authentication supports three modes: OIDC (Keycloak browser redirect), Direct Access Grant (username/password), and external Keycloak broker (federated IdP).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/auth/type` | Public | Returns auth type (`oidc` or `basic`) and Keycloak config status |
| POST | `/api/v1/auth/login` | Public | Login with username/password (Keycloak Direct Access Grant). Sets cookies. |
| POST | `/api/v1/auth/external/login` | Public | Login via external Keycloak identity provider broker |
| POST | `/api/v1/auth/logout` | Public | Logout — clears cookies, triggers Keycloak backchannel logout |
| POST | `/api/v1/auth/refresh` | Public | Refresh tokens using `refresh_token` cookie |
| GET | `/api/v1/auth/oidc/authorize` | Public | Get Keycloak OIDC authorization URL (query: `redirect_uri`, `kc_idp_hint`, `prompt`) |
| GET | `/api/v1/auth/oidc/callback` | Public | Handle OIDC callback — exchanges code for tokens, upserts user |
| GET | `/api/v1/auth/me` | JWT | Get current user's full profile with preferences |
| POST | `/api/v1/auth/sync-users` | `user:manage` | Sync all users and roles from Keycloak to local database |
| POST | `/api/v1/auth/register` | Public | Register new user (currently raises ValueError — managed by Keycloak) |

**Cookie-based auth:** Tokens stored in `access_token`, `refresh_token`, `id_token` HTTP-only cookies with `SameSite=Lax`.

**Token validation chain:** Local HS256 JWT → Keycloak JWKS → Keycloak userinfo → External Keycloak userinfo.

---

## Users

**Prefix:** `/api/v1/users`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/users/me` | JWT | Get own profile with preferences and personalization |
| GET | `/api/v1/users/me/permissions` | JWT | Get own resolved permissions |
| PATCH | `/api/v1/users/me` | JWT | Update own profile |
| POST | `/api/v1/users/me/password` | JWT | Change own password (raises ValueError — managed by Keycloak) |
| GET | `/api/v1/users/` | `user:list` | List users with pagination and filters (skip, limit, query, role, roles, is_active, invited) |
| POST | `/api/v1/users/` | `user:create` | Create user (local + Keycloak) |
| GET | `/api/v1/users/invited` | `user:list` | List pending invited users |
| GET | `/api/v1/users/download/csv` | `user:list` | Download users as CSV |
| POST | `/api/v1/users/invite` | `user:create` | Invite users by email (bulk) |
| POST | `/api/v1/users/{target_id}/role` | `user:update` | Set user role |
| POST | `/api/v1/users/{target_id}/reset-password` | `user:update` | Reset password (raises ValueError) |
| PATCH | `/api/v1/users/{target_id}/active` | `user:update` | Activate/deactivate user |
| POST | `/api/v1/users/{target_id}/password` | `user:update` | Set user password (raises ValueError) |
| GET | `/api/v1/users/{target_id}` | `user:read` | Get user by ID |
| PATCH | `/api/v1/users/{target_id}` | `user:update` | Update user profile |
| DELETE | `/api/v1/users/{target_id}` | `user:delete` | Delete user (local + Keycloak) |

**Response shape example (`GET /api/v1/users/`):**
```json
{
  "items": [{ "id": "...", "email": "...", "username": "...", "first_name": "...", "last_name": "...", "role": "...", "is_active": true }],
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

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/internal/users/upsert-from-keycloak` | JWT / Internal | Create/update user from Keycloak OIDC profile |
| GET | `/api/v1/internal/users/by-keycloak-id/{keycloak_id}` | JWT / Internal | Get user by Keycloak subject ID |
| PATCH | `/api/v1/internal/users/{target_id}` | JWT / Internal | Update user profile |
| GET | `/api/v1/internal/users/{target_id}/permissions` | JWT / Internal | Get user's permissions |
| POST | `/api/v1/internal/users/authorize` | JWT / Internal | Check if user has a specific permission |

---

## User Settings

**Prefix:** `/api/v1/users/me/settings`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/users/me/settings/` | `settings:read` | Get own settings |
| PATCH | `/api/v1/users/me/settings/` | `settings:update` | Update own settings |
| POST | `/api/v1/users/me/settings/prompt-shortcuts` | `settings:update` | Create prompt shortcut |
| PATCH | `/api/v1/users/me/settings/prompt-shortcuts/{shortcut_id}` | `settings:update` | Update prompt shortcut |
| DELETE | `/api/v1/users/me/settings/prompt-shortcuts/{shortcut_id}` | `settings:update` | Delete prompt shortcut |

### Settings — Internal

**Prefix:** `/api/v1/internal/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/internal/users/{target_id}/settings` | JWT / Internal | Get any user's settings |
| PATCH | `/api/v1/internal/users/{target_id}/settings` | JWT / Internal | Update any user's settings |
| POST | `/api/v1/internal/users/{target_id}/settings/prompt-shortcuts` | JWT / Internal | Create shortcut for any user |
| PATCH | `/api/v1/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}` | JWT / Internal | Update shortcut for any user |
| DELETE | `/api/v1/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}` | JWT / Internal | Delete shortcut for any user |

---

## User Memories

**Prefix:** `/api/v1/users/me/memories`

User memories store facts about the user for agent recall (long-term memory).

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/users/me/memories/` | `memory:read` | List memories (query: `page`, `page_size`) |
| POST | `/api/v1/users/me/memories/` | `memory:create` | Create memory (body: `{"content": "..."}`) — returns 201 |
| GET | `/api/v1/users/me/memories/{memory_id}` | `memory:read` | Get memory by ID |
| PATCH | `/api/v1/users/me/memories/{memory_id}` | `memory:update` | Update memory content |
| DELETE | `/api/v1/users/me/memories/{memory_id}` | `memory:delete` | Delete memory — returns 204 |
| DELETE | `/api/v1/users/me/memories/` | `memory:delete` | Delete all memories — returns `{"deleted": count}` |

### Memories — Internal

**Prefix:** `/api/v1/internal/users/{target_id}/memories`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/internal/users/{target_id}/memories` | JWT / Internal | List any user's memories |
| GET | `/api/v1/internal/users/{target_id}/memories/recall` | JWT / Internal | Get memories for agent recall (content-only strings) |
| POST | `/api/v1/internal/users/{target_id}/memories` | JWT / Internal | Create memory for any user |
| POST | `/api/v1/internal/users/{target_id}/memories/bulk` | JWT / Internal | Bulk add facts (body: `{"contents": [...], "source?": "..."}`) |
| GET | `/api/v1/internal/users/{target_id}/memories/{memory_id}` | JWT / Internal | Get specific memory |
| PATCH | `/api/v1/internal/users/{target_id}/memories/{memory_id}` | JWT / Internal | Update memory |
| DELETE | `/api/v1/internal/users/{target_id}/memories/{memory_id}` | JWT / Internal | Delete memory — 204 |
| DELETE | `/api/v1/internal/users/{target_id}/memories` | JWT / Internal | Delete all memories for user |

---

## API Keys

**Prefix:** `/api/v1/users/me/api-keys`

API keys are SHA-256 hashed and Fernet encrypted. The raw key is returned only once on creation.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/users/me/api-keys/` | `api_key:create` | Create API key (query: `name`). Returns `full_key` only once. |
| GET | `/api/v1/users/me/api-keys/` | `api_key:read` | List own API keys |
| DELETE | `/api/v1/users/me/api-keys/{key_id}` | `api_key:delete` | Revoke/delete API key |

---

## Coarse Roles

**Prefix:** `/api/v1/coarse-roles`

Coarse roles group permissions scoped to a service client.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/coarse-roles/` | `permission:list` | List coarse roles (query: `service_client`) |
| POST | `/api/v1/coarse-roles/` | `role:manage` | Create coarse role (query: `name`, `service_client`, `description?`) |
| GET | `/api/v1/coarse-roles/{role_name}` | `permission:list` | Get coarse role by name |
| PATCH | `/api/v1/coarse-roles/{role_name}` | `role:manage` | Update coarse role |
| DELETE | `/api/v1/coarse-roles/{role_name}` | `role:manage` | Delete coarse role |
| GET | `/api/v1/coarse-roles/{role_name}/permissions` | `permission:list` | Get permissions on role |
| PUT | `/api/v1/coarse-roles/{role_name}/permissions` | `role:manage` | Set permissions on role |
| GET | `/api/v1/coarse-roles/aggregated/` | `permission:list` | Aggregate permissions from multiple role names (query: `names` CSV) |
| GET | `/api/v1/coarse-roles/service-clients/list` | `permission:list` | List all service clients |

---

## Composite Roles

**Prefix:** `/api/v1/roles`

Composite roles aggregate coarse roles and permissions. Changes to composite roles invalidate user sessions.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/roles/` | `role:list` | List all composite roles |
| POST | `/api/v1/roles/` | `role:manage` | Create composite role (body: `name`, `description?`, `permissions?`, `role_ids?`) |
| GET | `/api/v1/roles/{role_name}` | `role:read` | Get composite role by name |
| PATCH | `/api/v1/roles/{role_name}` | `role:manage` | Update composite role |
| DELETE | `/api/v1/roles/{role_name}` | `role:manage` | Delete composite role (blocked if built-in or users assigned) |
| GET | `/api/v1/roles/{role_name}/permissions` | `role:read` | Get effective permissions (direct + aggregated) |
| PUT | `/api/v1/roles/{role_name}/permissions` | `role:manage` | Set permissions |
| GET | `/api/v1/roles/{role_name}/role-ids` | `role:read` | Get coarse role references |
| PUT | `/api/v1/roles/{role_name}/role-ids` | `role:manage` | Set coarse role references |
| POST | `/api/v1/roles/sync-keycloak` | `role:manage` | Sync all roles to Keycloak |

---

## Permissions

**Prefix:** `/api/v1/permissions`

Permissions are synced from service manifests (user-service, agent-service, rag-service, tools-service).

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/permissions/` | `permission:list` | List permissions (query: `service` filter) |
| GET | `/api/v1/permissions/entities` | `permission:list` | List all unique permission entities |
| GET | `/api/v1/permissions/services` | `permission:list` | List services with permission counts |
| POST | `/api/v1/permissions/sync` | `permission:manage` | Sync permissions from all service manifests |
| GET | `/api/v1/permissions/{permission_name}` | `permission:read` | Get permission by name |

---

## System Settings

**Prefix:** `/api/v1/system-settings`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/system-settings/keycloak` | System Admin | Get full Keycloak configuration |
| PATCH | `/api/v1/system-settings/keycloak` | System Admin | Update Keycloak configuration (fields encrypted before storage) |
| PATCH | `/api/v1/system-settings/keycloak/realm-session` | System Admin | Update Keycloak realm session token lifespans |
| POST | `/api/v1/system-settings/keycloak/external-idp/sync` | System Admin | Sync external identity provider to Keycloak |

---

## Auth dependency hierarchy

```
require_auth_or_internal_service_token
  └─ get_current_user_id (token from header or cookie)
      └─ returns "internal-service" for X-Internal-Service-Token

require_auth                → get_current_user_id → raises 401 if None
require_admin               → require_auth → checks superuser or admin role
require_system_admin        → require_auth → checks superuser or system-admin role
require_permission("perm")  → require_auth → checks DB role permissions + coarse role aggregation
```

**Superuser detection:** A user with `["*"]` permissions bypasses all permission checks (wildcard).

---

## Keycloak architecture

Keycloak is the source of truth. The service mirrors user data, roles, and permissions to a local PostgreSQL database.

- **User CRUD** → creates/updates/deletes in both Keycloak and local DB
- **Role management** → Composite roles in DB, synced to Keycloak realm roles + client roles
- **Password management** → Delegated entirely to Keycloak (service raises `ValueError`)
- **Token validation** → 4-step fallback chain: local HS256 → JWKS → userinfo → external Keycloak
- **Login** → Keycloak Direct Access Grant or OIDC redirect
- **External IdP** → Keycloak identity provider broker with federated identity bridging
