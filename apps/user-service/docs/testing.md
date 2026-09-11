# User service testing

Use this document to choose validation for user-service changes.

## Commands

Run commands from `apps/user-service/`.

```sh
make test
make lint
make typecheck
make validate
```

Use focused pytest paths while developing when the changed behavior is narrow.
Run `make validate` before marking the service change ready.

## Focus areas

- Auth flows: tests covering login, refresh, logout, OIDC, and external login.
- RBAC: role, permission, feature-bundle, and effective-permission tests.
- Persistence: repository and migration-sensitive tests.

Run `make quality-staged` from the repository root before committing or pushing.
