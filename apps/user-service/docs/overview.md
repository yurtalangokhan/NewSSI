# User service overview

User service owns authentication, users, roles, permissions, settings, API keys,
and user memories. Other services call user-service to resolve caller identity
and effective permissions.

## Source map

| Area | Location |
|---|---|
| FastAPI routes | `src/api/` |
| Controllers | `src/controller/` |
| Business services | `src/service/` |
| Repositories | `src/repository/` |
| Database and migrations | `src/core/db/` |
| Schemas | `src/schema/` |
| Tests | `tests/` |

## Documentation

- [Architecture](architecture.md) describes auth and RBAC boundaries.
- [API](api.md) lists endpoint contracts.
- [Testing](testing.md) describes validation commands.
- [Runbook](runbook.md) covers startup, migrations, and operational checks.
