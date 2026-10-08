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

With Keycloak enabled, startup uses the configured admin credentials to enable
Authorization Services on existing application service clients before projecting
resource grants. This does not require a gateway client secret. Startup enforces
authorization, disables remote resource management, and removes Keycloak's default
allow-all objects while preserving custom policies and client configuration.
Repeated startup safely completes partial initialization under the shared Redis
policy lock. Public service clients, missing resource clients, and failed Keycloak
operations stop startup rather than bypass permission synchronization.

Resource projection skips grants whose user no longer exists in Keycloak,
without deleting their SQL records. Global and scoped projection check each
distinct user once per inventory read. Existing users, including disabled
accounts, retain their grants; lookup errors still stop synchronization.

## `agenticai-v1` authorization resources

The `agenticai-v1` realm uses `*-service-client` Keycloak clients. Its URI
resources and scope policies are projected from
`configs/apisix/gateway-policies.json` by a separate operator command. Run
from `apps/user-service/` with the normal Keycloak admin configuration:

```sh
uv run python -m scripts.provision_v1_authorization
uv run python -m scripts.provision_v1_authorization --apply
```

The first command previews resource, URI, scope, and grant counts. The apply
command backs up each affected resource server under
`.tmp/authorization-resources/backups/`, removes Keycloak's default wildcard
allow objects, imports role-backed scope policies, replaces associations on
existing scope permissions, and verifies the resulting resources and policy links.
It refuses unrelated existing authorization objects. The tools MCP routes are
authenticated by Gateway and have URI metadata but no invented scope grant.
This operation targets only `agenticai-v1`. The local application and Gateway
configuration now use that realm and its `web-client` and `*-service-client`
clients. Existing Keycloak users and assignments are not copied from the old
realm by this operation. A stored Keycloak configuration in user-service's
system settings takes precedence over `.env`; update its realm, issuer, login
client, and service client values during cutover.
For external login, also synchronize the external identity provider in the new
realm using System Settings. Keep the existing external client secret configured
there and register the new realm's broker callback with the external client.
The old realm's provider is not automatically copied during authorization
provisioning. Without it, Keycloak can return its internal login form even when
the request includes the external provider hint.
Set `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_LOGIN_CLIENT_ID`, and
all four `KEYCLOAK_*_SERVICE_CLIENT_ID` values in the central `configs/.env`.
Missing identifiers stop startup instead of selecting an implicit client.

### Existing Connectors admin access

The Existing Connectors page requires `datasource:view`. This UI-only grant
belongs to the RAG `knowledge-manager` client role, alongside its
`datasource:read` grant. It is stored in the role's `agentic.permissions`
attribute, like `embedding:view`; no gateway route requires a `view` scope.
The `enterprise-admin` composite role inherits `knowledge-manager` and the
service admin bundles.

Run the guarded, repeatable grant command from `apps/user-service/`. The first
command previews a missing grant, and the second adds it while preserving the
role's other attributes:

```sh
uv run python scripts/grant_datasource_view.py
uv run python scripts/grant_datasource_view.py --apply
```

### Enterprise administrator grants

The `enterprise-admin` realm role inherits the agent, RAG, tooling, and access
admin client roles so its effective grants cover the managed service catalog.
The agent-service admin role also carries UI-only page views for mail settings,
MCP actions, model providers, and web search. System Settings permissions stay
excluded. Existing manager bundle assignments remain in place.

Preview and reconcile these grants after provisioning or changing built-in
client roles:

```sh
uv run python -m scripts.reconcile_enterprise_admin
uv run python -m scripts.reconcile_enterprise_admin --apply
```

The command checks every managed client-role grant and registered gateway scope
before writing and is safe to repeat. It assigns each registered scope to its
own service's admin role and excludes `system.settings:*`. Page views are role
attributes; they do not create gateway scopes. After an applied change, run
`uv run python -m scripts.provision_v1_authorization --apply` to update the
Keycloak role-backed scope policies.

### End-user memory settings access

Chat Preferences calls the personal-memory CRUD routes on user-service. The
`enduser` realm role inherits `account-self-service`, which needs
`memory:create`, `memory:read`, `memory:update`, and `memory:delete` in its
`user-service-client` role attributes. The RAG memory-index scopes remain on
`rag-service-client` and are not granted by this repair.

Preview and apply the repeatable grant, then refresh existing Keycloak scope
policy associations:

```sh
uv run python -m scripts.grant_enduser_memory
uv run python -m scripts.grant_enduser_memory --apply
uv run python -m scripts.provision_v1_authorization --apply
```

## Migrations

Use the service Makefile for Alembic operations.

```sh
make db-migrate
make db-migrate-create NAME="describe_change"
make db-migrate-rollback
```

Do not edit applied migrations to change production behavior. Add a new
migration instead.

## Keycloak identity cutover

Revision `0049` removes runtime SQL identity tables after import and verified
reconciliation with Keycloak. The application keeps its settings, keys,
memories, audit records, and resource grants. If startup stops because the
identity manifest is missing, complete import, reconciliation, and the guarded
Alembic upgrade below. Do not bypass the manifest gate.

Before importing identities or generating a reconciliation manifest, apply the
SQL permission repair while application and identity writers are stopped:

```sh
uv run alembic upgrade 0048_flow_permissions
```

The repair changes identity snapshot data. Generate a fresh manifest after it
runs; a manifest from revision `0048` will fail the cutover digest check.

The incoming branch also used revision `0049` for a different SQL permission
repair. If a deployed database reports `0049`, inspect its schema, migration
history, and identity archive before proceeding. The revision string alone
cannot distinguish that repair from the Keycloak cutover. Assess and reconcile
the deployment's migration state before applying this graph; do not blindly
stamp the database or assume that the cutover has already run.

### Prepare mappings

Run commands from `apps/user-service/` with the normal service database and
Keycloak configuration loaded. Both CLIs load persisted runtime settings before
connecting to Keycloak; they don't rely only on environment defaults. The
Keycloak administrator needs `manage-realm` permission for identity import.
Verification also needs permission to query users, groups, role catalogs, and
their assignments, including enabled clients' service-account endpoints. The
verifier identifies service accounts through those endpoints because ordinary
user listings can omit them and their profiles can omit the service-account
marker. An unknown application user still stops verification.
Runtime hierarchy reads use the group query and view
permissions.

Supply three environment variables containing the user, agent, and RAG database
URLs, using the async `postgresql+asyncpg` driver. The examples use
`CUTOVER_USER_DB_URL`, `CUTOVER_AGENT_DB_URL`, and `CUTOVER_RAG_DB_URL`; these
are command inputs, not new application settings. The normal service database
configuration must point to the same database as `CUTOVER_USER_DB_URL`, because
import and runtime-settings loading use that configuration. Read hosts, ports,
database names, and credentials from deployment configuration. Keep credentials,
mapping files, and manifests out of version control.

Before importing, take coordinated, restorable backups of Keycloak and all
affected databases. Stop application, worker, scheduled, and identity
administration writes. Keep them stopped until the cutover checks finish. The
`--writers-stopped` flag records this prerequisite; it doesn't stop processes.

Import missing identities and write their verified UUID mappings:

```sh
uv run python -m src.core.database.import_identity \
  --output identity-mappings.json --batch-size 500 --concurrency 4 \
  --apply --writers-stopped
```

Import includes all legacy users and organizations, including load-test records.
It creates missing role definitions and composite links, imports missing groups
and users in batches, and adds missing legacy assignments to accounts with
recorded Keycloak subjects. Existing credentials and additional assignments
remain intact. New accounts preserve legacy `created_at` as Keycloak
`createdTimestamp`; the importer never generates passwords. An unmapped account
with a legacy password hash requires a supported credential migration and stops
the import instead of silently dropping that credential.

Built-in role protection is stored on each Keycloak role as the
`agentic.builtin` attribute with value `true`. This applies to both realm
composite roles and service-client feature roles. An absent attribute or
`false` means custom. Before enabling role deletion, mark existing built-in
feature roles in Keycloak; the application cannot infer their provenance from
their names or permissions. The identity import and reconciliation write the
marker when the source role row explicitly has `is_builtin=true`.

You can repeat the import command after an interruption against the same source
database. The importer checks `agentic.legacy_identity_id` provenance in
Keycloak before creating another identity. It rejects username, email, and
identity collisions rather than merging unrelated accounts. The output mapping
file is replaced atomically after import and assignment checks complete. Import
doesn't rewrite application references, drop SQL tables, or produce a manifest
that authorizes `0049`.

The generated mapping file has this structure. If all identities already exist,
you can instead prepare reviewed mappings with the same structure:

```json
{
  "users": {
    "00000000-0000-0000-0000-000000000001": "00000000-0000-0000-0000-000000000002"
  },
  "organizations": {
    "00000000-0000-0000-0000-000000000003": "00000000-0000-0000-0000-000000000004"
  }
}
```

Keys are legacy local IDs; values are existing Keycloak subject or group IDs.
Replace every example ID. Reconciliation fills missing user entries only from
recorded `users.keycloak_id` values. Organizations and users without a recorded
subject need explicit mappings. Include historical audit actors when necessary.
Reconciliation doesn't create identities or guess mappings from names or email
addresses; use the import step for missing identities.

Run the read-only preflight, choosing an output path that does not already
exist:

```sh
uv run python -m src.core.database.reconcile_identity \
  --mapping identity-mappings.json --output identity-dry-run.json \
  --user-db-env CUTOVER_USER_DB_URL \
  --agent-db-env CUTOVER_AGENT_DB_URL --rag-db-env CUTOVER_RAG_DB_URL
```

Preflight reads full user profiles and group representations in pages. Group
reads send an explicit empty `search` with `populateHierarchy=false`, so each
page includes groups at every depth. They verify the realm-wide group count,
rebuild ancestry from parent IDs, and reject missing parents, cycles, or
inconsistent child counts. Role catalogs and composite links use their dedicated
endpoints. Preflight indexes group membership and effective realm roles,
including inherited and composite grants, without one verification request per
user. These indexes contain actual Keycloak read-back data. Writes invalidate
the affected inventory, which is refreshed before verification; submitted
payloads aren't accepted as proof of persistence.

Runtime organization listings use the same flat group pages. They don't attempt
a full realm export: large group hierarchies can make partial export fail with
HTTP `500` or exceed request timeouts even when paginated reads work.

Preflight checks role and organization metadata and external ownership
references. It rejects unmapped IDs, conflicting permissions or memberships, and
unregistered SQL identity columns. The role and service-client catalog must
match the explicit legacy names. The dry-run output cannot authorize `0049`.

### Explicit orphan-reference exceptions

If an external ownership value has no corresponding legacy or Keycloak user, you
can explicitly preserve that orphan value with `--ignore-external-user-id`.
Repeat the option for each reviewed exception. For example, use generic orphan
identifiers in a preflight command:

```sh
uv run python -m src.core.database.reconcile_identity \
  --mapping identity-mappings.json --output identity-orphans-dry-run.json \
  --user-db-env CUTOVER_USER_DB_URL \
  --agent-db-env CUTOVER_AGENT_DB_URL --rag-db-env CUTOVER_RAG_DB_URL \
  --ignore-external-user-id archived-owner-a \
  --ignore-external-user-id archived-owner-b
```

Replace those values with the exact reviewed orphan identifiers. Repeat the same
options when applying reconciliation; the CLI doesn't inherit exceptions from a
previous output file. The manifest records them as `ignored_external_user_ids`.
Only those external reference values remain unchanged. Other references in the
same row still undergo normal mapping and validation. An exception doesn't
create an account, transfer ownership, grant access, or permit ignoring a known
legacy or Keycloak user. It doesn't bypass the remaining cutover checks.

### Apply and deploy

Keep application and identity administration writers stopped throughout this
sequence. The `--writers-stopped` flag records this operational prerequisite;
the command does not stop processes for you.

1. Confirm backups, stopped writers, and a completed import or reviewed mapping
   file. Resolve all preflight conflicts against the Keycloak identities and
   assignments. Carry any reviewed orphan-reference options into the next
   command.
2. Apply reconciliation with a new output filename:

   ```sh
   uv run python -m src.core.database.reconcile_identity \
     --mapping identity-mappings.json --output identity-ready.json \
     --user-db-env CUTOVER_USER_DB_URL \
     --agent-db-env CUTOVER_AGENT_DB_URL --rag-db-env CUTOVER_RAG_DB_URL \
     --apply --writers-stopped
   ```

3. Run the guarded revision using the same user-service database configuration
   and Keycloak realm. Substitute the absolute manifest path:

   ```sh
   uv run alembic \
     -x identity_manifest=/absolute/path/identity-ready.json upgrade head
   ```

4. Start the updated services. Verify login, role and organization management,
   inherited access, settings, memories, API keys, chat ownership, and
   collection access before reopening writes.

Apply declares administrator-managed user attributes, transfers missing
application metadata, and verifies the resulting Keycloak values. It preserves
actual identities and assignments. It then rewrites known external scalar,
array, and JSON ownership fields in transactional database updates. A failed
later database can be retried while writers remain stopped; already rewritten
IDs are unchanged. Each database transaction is separate from Keycloak writes.

The ready manifest binds reconciliation to a digest of every local identity row.
Revision `0049` checks that digest, the configured realm, every retained user
and group reference, and incoming foreign keys before changing data. It locks
the affected user-service tables, archives complete identity rows and the
manifest in `identity_cutover_archive`, removes retained identity foreign keys,
rewrites references, and drops identity tables without `CASCADE`. The revision
makes no network calls. Missing mappings, stale source data, unique-key
collisions, or unexpected dependencies abort the transaction.

Audit targets can refer to deleted users or organizations. Known targets are
remapped to Keycloak IDs; historical targets absent from both identity stores
retain their original event identifiers and are recorded in the archived
manifest. This exception applies only to audit targets. Audit actors, active
ownership, and resource grants still require resolved identities.

### New databases and recovery

A new database also passes through the historical schema. Run migrations only
through `0048_flow_permissions`, then complete the same import, reconciliation, and guarded
upgrade sequence. An empty user/group set can use empty mapping objects;
historical permission and role metadata still require preflight. Startup and
`make db-migrate` cannot bypass the `0049` manifest gate.

```sh
uv run alembic upgrade 0048_flow_permissions
```

Revision `0049` has no automatic downgrade. Its archive preserves source rows
for investigation, but it does not reverse Keycloak metadata or external
database rewrites and is not a complete application backup. Restore the
coordinated pre-cutover backups and matching application version to roll back.
An existing archive schema causes the revision to stop rather than overwrite
recovery data. Do not use `db-reset` or automatic downgrade for this cutover.

## Organization load fixtures

The historical `scripts/seed_organization_load_test.py` SQL `seed` and `cleanup`
operations now refuse execution before database or Keycloak I/O. They cannot
create or delete identities after Keycloak assumes ownership. The deterministic
offline fixture generator remains available for tests. Use the supported
Keycloak-backed management APIs to create any required live test identities.
