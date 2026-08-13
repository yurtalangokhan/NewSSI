# User Service

User Management Microservice — Auth, Users, Roles, Permissions

## Generate organization load-test data

The load-test seed command creates a deterministic organization hierarchy,
direct organization members, unit managers, and shared visual diagram
positions. Run it from `apps/user-service` after applying database migrations.

The default dataset contains 10,000 organizations and 100,000 users:

```sh
uv run python scripts/seed_organization_load_test.py seed
```

Customize the dataset when you need a different load profile:

```sh
uv run python scripts/seed_organization_load_test.py seed \
  --organizations 50000 \
  --users 1000000 \
  --max-depth 8 \
  --batch-size 10000 \
  --seed organization-page-million-users
```

The command replaces an earlier load-test dataset before inserting the new
one. It doesn't delete normal users or organizations. When a normal root
organization exists, the generated hierarchy is attached beneath it.

Remove the generated dataset with this command:

```sh
uv run python scripts/seed_organization_load_test.py cleanup
```

<!-- prettier-ignore -->
> [!WARNING]
> Load-test records use organization codes beginning with `LOADTEST_` and user
> email addresses in the reserved `loadtest.invalid` domain. Don't use either
> namespace for normal development data.
