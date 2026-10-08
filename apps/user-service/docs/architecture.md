# User service architecture

User service follows the shared FastAPI layered architecture. Routes stay thin,
controllers orchestrate, services own business logic, and repositories wrap
Keycloak admin clients or async SQLAlchemy access for application data.

## Request flow

The existing service facade preserves the frontend management APIs.

```text
src/api -> src/controller -> src/service -> src/repository
```

Controllers translate domain errors to HTTP responses. Services raise domain
exceptions and must not depend on FastAPI delivery types.

## Authorization

Keycloak owns users, realm composite roles, client feature roles, permission
metadata, and role assignments. Runtime checks expand effective assignments,
including group inheritance, through the Keycloak adapters. The `system-admin`
wildcard role resolves to all permissions. JWTs remain compact role markers.

The assignable permission catalog includes managed Keycloak feature-resource
scopes even when no role currently grants them. Client-role attributes also
contribute UI-only permissions. Resource scopes retain their owning service
client; listing a permission does not grant it to a role or user. Instance
resource scopes are excluded from this feature catalog.

The LLM `provider` resource and its `read` scope belong to
`agent-service-client`. Grant provider permissions through the Agent Workspace
feature roles on that same client, inherited through their assigned realm
roles. A resource and scope alone do not grant
access; the scope permission must link to the granting role policies.

Policy reconciliation imports dependencies, then explicitly updates existing
managed scope permissions to replace their resource, scope, and role-policy
associations. It preserves their IDs, resource URIs, and unmanaged policies.
All policy writes use the shared Redis lock.

Every role is identified by its Keycloak-generated, immutable role `id`. The
role-management, feature-bundle, and user-role-assignment APIs address roles
only by that ID; they don't fall back to names or keep a copied ID attribute.
Composite role responses expose feature-role IDs in `role_ids`, and
`role_names` provides display names. Role names are resolved only where
Keycloak speaks in names: realm-role claims in access tokens, uniqueness checks
on create, and organization membership roles. Repositories return immutable
`CompositeRoleRecord` and `CoarseRoleRecord` values.

The API's primary role is a projection of Keycloak assignments and application
attributes. No local `users`, `user_roles`, role, or permission tables participate
in runtime authorization. Login and refresh do not mirror identities into SQL.

## Identity and organization ownership

User IDs equal Keycloak subjects; organization IDs equal Keycloak group IDs.
Nested groups define the organization hierarchy. Namespaced group attributes
hold application organization metadata. Administrator-managed user attributes
hold primary organization and membership metadata. Actual Keycloak memberships
and role assignments remain authoritative.

Organization member role APIs project platform roles, including the existing
`role_in_org` compatibility field. Unit Manager assignments define management
authority over the user's active units. Removing membership does not remove a
platform role.

PostgreSQL retains settings, API keys, memories, audit logs, and resource grants.
Their user and organization UUIDs are external Keycloak references without
foreign keys or ORM relationships to local identity tables. Resource grants
continue to participate in organization-scoped access checks.

The [cutover runbook](runbook.md#keycloak-identity-cutover) describes the guarded
reference reconciliation, metadata transfer, recovery archive, and migration.

## Connector configurations

`user_connector_configs` holds the source configurations agent-service syncs
with, one row per configuration, owned by the user who created it. The service
layer seals the whole configuration document as one Fernet token under
`SecretScope.CONNECTOR_CONFIG`; the repository only ever sees ciphertext.

The routes are internal-only (`require_internal_service_token`). Unlike the
other `/internal/users/...` routes they do not accept a user JWT, because the
single-item read returns decrypted credentials. Mutating responses carry
metadata only, so nothing secret reaches the idempotency replay cache. The row
has no foreign key to a user record: a principal without a user-service id
(agent-service's development user) owns its rows under a derived UUID.
