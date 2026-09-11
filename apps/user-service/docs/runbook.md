# User service runbook

Use this runbook for local startup, database migrations, and auth operations.

## Startup

Run these commands from `apps/user-service/`.

```sh
make dev-install
make run
```

User service needs its database and configured auth provider for full runtime
flows. Health and readiness endpoints are documented in [api.md](api.md).

## Migrations

Use the service Makefile for Alembic operations.

```sh
make db-migrate
make db-migrate-create NAME="describe_change"
make db-migrate-rollback
```

Do not edit applied migrations to change production behavior. Add a new
migration instead.
