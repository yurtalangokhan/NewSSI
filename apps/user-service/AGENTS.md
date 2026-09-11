# User service index

Use this file only for work under `apps/user-service/`. Root `AGENTS.md` owns
the workflow; this file routes identity work to code, tests, and documentation.

## Ownership and source map

User service owns authentication, users, roles, permissions, settings, API
keys, memories, and Keycloak integration.

```text
src/api/routes/              HTTP routes
src/api/dependencies.py      Auth dependencies
src/controller/              Use-case orchestration
src/service/                 Business logic and Keycloak coordination
src/repository/              Async SQLAlchemy access
src/schema/                  Request and response schemas
src/core/database/           Engine and sessions
src/core/db/                 Models and Alembic migrations
src/core/exceptions.py       Domain failures
src/core/permissions/        Permission resolution
src/core/idempotency.py      Idempotency
src/config.py                Configuration
src/main.py                  Application factory
tests/                       Tests by route, controller, service, and repository
```

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| API or schema | `src/api/routes/`, `src/schema/` | Matching route/controller tests |
| Auth or Keycloak flow | Route, controller, then `src/service/` | Login/OIDC/refresh/logout tests |
| RBAC | `src/core/permissions/`, service | Role/permission/effective-access tests |
| Persistence | `src/repository/`, `src/core/db/` | Repository and migration tests |
| API keys, settings, or memories | Matching route/service/repository | Matching domain tests |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Public endpoint, schema, or response changes | `docs/api.md` |
| Auth, persistence, or layer boundary changes | `docs/architecture.md` |
| Test scope is unclear | `docs/testing.md` |
| Startup, Keycloak, database, or operations change | `docs/runbook.md` |
| Service ownership is unclear | `docs/overview.md` |

## Invariants

- Preserve `route -> controller -> service -> repository` and async I/O.
- Keep FastAPI types out of services and persistence out of services.
- Preserve `_to_dict()` response serialization unless explicitly changed.
- Preserve Keycloak boundaries and `system-admin` wildcard behavior.
- Treat `users.role` as a derived mirror, not the source of truth.
- Use shared domain exceptions and `from i18n import t` for user-facing text.
- Use Ruff line length 100 and existing migration commands.

## Test scope

Use `uv run pytest <matching-test-path>` inside quiet task/spec wrappers. A
contract change expands coverage to every affected auth, RBAC, or persistence
test group. Full `make validate` runs only through the push wrapper.
