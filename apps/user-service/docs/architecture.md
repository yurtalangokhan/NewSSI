# User service architecture

User service follows the shared FastAPI layered architecture. Routes stay thin,
controllers orchestrate, services own business logic, and repositories wrap
async SQLAlchemy access.

## Request flow

```text
src/api -> src/controller -> src/service -> src/repository
```

Controllers translate domain errors to HTTP responses. Services raise domain
exceptions and must not depend on FastAPI delivery types.

## Authorization

Runtime authorization is permission based. Users receive roles through
`user_roles`; roles resolve direct permissions and feature bundles. The
`system-admin` wildcard role resolves to all permissions. The legacy
`users.role` field is a derived primary-role mirror for older readers.

## External identity

Keycloak integration lives behind service and client modules. Login, refresh,
OIDC callback, external identity-provider sync, and role synchronization must
preserve existing local role assignments unless a task explicitly changes the
authorization contract.
